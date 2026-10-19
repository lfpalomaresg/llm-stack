#!/usr/bin/env python3
"""Tests de opencode-watchdog.py (unittest, stdlib).

Logs sintéticos en un directorio temporal; killer, notificador, lista de procesos y
comprobación lsof inyectados: ningún test toca procesos reales ni lanza osascript.

Ejecutar:  /usr/bin/python3 ~/llm-stack/test-opencode-watchdog.py -v
"""
import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "opencode_watchdog", os.path.join(HERE, "opencode-watchdog.py"))
wd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wd)

# Instante base fijo (UTC) para los logs sintéticos.
T0 = datetime(2026, 10, 17, 0, 0, 0, tzinfo=timezone.utc).timestamp()
RUN = "ca48fd62"
PID = 4242
OPENCODE_BIN = "/Users/pifanmac/.opencode/bin/opencode"


def iso(t):
    return datetime.fromtimestamp(t, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.") + "%03dZ" % int(round((t % 1) * 1000))


def start_line(t, run=RUN):
    return ('timestamp=%s level=INFO run=%s message="creating instance" '
            'directory=/Users/pifanmac' % (iso(t), run))


def err_line(t, sid, run=RUN):
    return ('timestamp=%s level=ERROR run=%s message="stream error" providerID=llm-stack '
            'modelID=local-worker session.id=%s small=false agent=worker mode=subagent '
            'error.error="AI_APICallError: litellm.APIConnectionError: Model unloaded."'
            % (iso(t), run, sid))


def cmp_line(t, sid, run=RUN):
    return ('timestamp=%s level=INFO run=%s message=stream providerID=llm-stack '
            'modelID=local-worker session.id=%s small=false agent=compaction mode=primary'
            % (iso(t), run, sid))


def normal_line(t, sid, run=RUN):
    return ('timestamp=%s level=INFO run=%s message=stream providerID=llm-stack '
            'modelID=local-worker session.id=%s small=false agent=build mode=primary'
            % (iso(t), run, sid))


class FakeKiller:
    def __init__(self):
        self.calls = []

    def __call__(self, proc):
        self.calls.append(proc)
        return "SIGTERM"


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="ocwd-test-")
        self.log = os.path.join(self.dir, "opencode.log")
        self.state = os.path.join(self.dir, "state", "state.json")
        self.actions = os.path.join(self.dir, "opencode-watchdog.log")
        self.killer = FakeKiller()
        self.notes = []
        self.out = io.StringIO()
        # Proceso opencode cuyo arranque (lstart, resolución de segundo) es 1 s antes
        # de la primera línea de su run=.
        self.procs = [(PID, T0 - 1.0, OPENCODE_BIN)]
        self.holds = lambda pid, path: True
        self.write([start_line(T0)])

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def write(self, lines, mode="a", newline=True):
        with open(self.log, mode) as f:
            for i, ln in enumerate(lines):
                f.write(ln)
                if newline or i < len(lines) - 1:
                    f.write("\n")

    def run_wd(self, now, dry_run=False):
        return wd.run_once(
            self.log, self.state, self.actions, dry_run=dry_run, now=now,
            killer=self.killer, notifier=self.notes.append,
            proc_lister=lambda: list(self.procs), holds_log=self.holds,
            out=self.out)

    def action_text(self):
        if not os.path.exists(self.actions):
            return ""
        with open(self.actions) as f:
            return f.read()

    def init(self):
        """Primera ejecución: se posiciona al final del log sin actuar."""
        rc = self.run_wd(now=T0 + 5)
        self.assertEqual(rc, 0)
        self.assertEqual(self.killer.calls, [])


class TestErrorLoop(Base):
    def test_error_loop_triggers(self):
        self.init()
        self.write([err_line(T0 + 10 + i * 5, "ses_loop") for i in range(15)])
        rc = self.run_wd(now=T0 + 120)
        self.assertEqual(rc, 0)
        self.assertEqual([p[0] for p in self.killer.calls], [PID])
        txt = self.action_text()
        self.assertIn("ses_loop", txt)
        self.assertIn("run=%s" % RUN, txt)
        self.assertIn("pid=%d" % PID, txt)
        self.assertIn("stream error", txt)
        self.assertEqual(len(self.notes), 1)

    def test_fourteen_errors_do_not_trigger(self):
        self.init()
        self.write([err_line(T0 + 10 + i * 5, "ses_loop") for i in range(14)])
        self.run_wd(now=T0 + 120)
        self.assertEqual(self.killer.calls, [])
        self.assertEqual(self.action_text(), "")

    def test_window_persists_across_executions(self):
        self.init()
        self.write([err_line(T0 + 10 + i * 5, "ses_loop") for i in range(8)])
        self.run_wd(now=T0 + 60)
        self.assertEqual(self.killer.calls, [])
        self.write([err_line(T0 + 70 + i * 5, "ses_loop") for i in range(7)])
        self.run_wd(now=T0 + 120)
        self.assertEqual([p[0] for p in self.killer.calls], [PID])

    def test_acts_only_once_per_session(self):
        self.init()
        self.write([err_line(T0 + 10 + i, "ses_loop") for i in range(40)])
        self.run_wd(now=T0 + 60)
        self.assertEqual(len(self.killer.calls), 1)
        self.assertEqual(len(self.action_text().splitlines()), 1)
        # Siguiente pasada con más errores de la misma sesión: sigue en enfriamiento.
        self.write([err_line(T0 + 60 + i, "ses_loop") for i in range(20)])
        self.run_wd(now=T0 + 120)
        self.assertEqual(len(self.killer.calls), 1)
        self.assertEqual(len(self.action_text().splitlines()), 1)


class TestCompactionLoop(Base):
    def test_compaction_loop_triggers(self):
        self.init()
        self.write([cmp_line(T0 + 10 + i * 20, "ses_cmp") for i in range(12)])
        self.run_wd(now=T0 + 300)
        self.assertEqual([p[0] for p in self.killer.calls], [PID])
        self.assertIn("compaction", self.action_text())

    def test_eleven_compactions_do_not_trigger(self):
        self.init()
        self.write([cmp_line(T0 + 10 + i * 20, "ses_cmp") for i in range(11)])
        self.run_wd(now=T0 + 300)
        self.assertEqual(self.killer.calls, [])
        self.assertEqual(self.action_text(), "")

    def test_agent_compaction_inside_quoted_text_is_ignored(self):
        # Caso real: el texto de un error lleva "agent=compaction" dentro de comillas.
        self.init()
        lines = [('timestamp=%s level=ERROR run=%s message="litellm.APIConnectionError: '
                  'boom agent=compaction session.id=ses_fake" session.id=ses_x agent=build'
                  % (iso(T0 + 10 + i), RUN)) for i in range(20)]
        self.write(lines)
        self.run_wd(now=T0 + 60)
        self.assertEqual(self.killer.calls, [])
        self.assertEqual(self.action_text(), "")


class TestWindow(Base):
    def test_scattered_errors_outside_window_do_not_trigger(self):
        self.init()
        # 40 errores, uno cada 60 s (40 min): nunca más de 11 dentro de 10 min.
        self.write([err_line(T0 + 10 + i * 60, "ses_slow") for i in range(40)])
        self.run_wd(now=T0 + 10 + 40 * 60)
        self.assertEqual(self.killer.calls, [])
        self.assertEqual(self.action_text(), "")

    def test_two_sessions_do_not_add_up(self):
        self.init()
        lines = []
        for i in range(10):
            lines.append(err_line(T0 + 10 + i * 5, "ses_A"))
            lines.append(err_line(T0 + 11 + i * 5, "ses_B"))
        self.write(lines)
        self.run_wd(now=T0 + 120)
        self.assertEqual(self.killer.calls, [])
        self.assertEqual(self.action_text(), "")

    def test_mixed_errors_and_compactions_do_not_add_up(self):
        self.init()
        lines = [err_line(T0 + 10 + i, "ses_m") for i in range(10)]
        lines += [cmp_line(T0 + 30 + i, "ses_m") for i in range(10)]
        self.write(lines)
        self.run_wd(now=T0 + 120)
        self.assertEqual(self.killer.calls, [])
        self.assertEqual(self.action_text(), "")


class TestOffset(Base):
    def test_first_run_positions_at_end_without_acting(self):
        self.write([err_line(T0 + 10 + i, "ses_hist") for i in range(50)])
        rc = self.run_wd(now=T0 + 100)
        self.assertEqual(rc, 0)
        self.assertEqual(self.killer.calls, [])
        with open(self.state) as f:
            st = json.load(f)
        self.assertEqual(st["offset"], os.path.getsize(self.log))

    def test_offset_avoids_reprocessing(self):
        self.init()
        self.write([err_line(T0 + 10 + i, "ses_r") for i in range(10)])
        self.run_wd(now=T0 + 30)
        self.run_wd(now=T0 + 31)   # sin líneas nuevas: si releyera, sumaría 20
        self.run_wd(now=T0 + 32)
        self.assertEqual(self.killer.calls, [])
        self.write([err_line(T0 + 40 + i, "ses_r") for i in range(4)])  # total real 14
        self.run_wd(now=T0 + 60)
        self.assertEqual(self.killer.calls, [])
        self.write([err_line(T0 + 50, "ses_r")])                         # 15
        self.run_wd(now=T0 + 61)
        self.assertEqual(len(self.killer.calls), 1)

    def test_partial_last_line_waits_until_complete(self):
        self.init()
        lines = [err_line(T0 + 10 + i, "ses_p") for i in range(15)]
        self.write(lines[:14])
        partial = lines[14]
        with open(self.log, "a") as f:
            f.write(partial[:40])           # línea a medio escribir
        self.run_wd(now=T0 + 40)
        self.assertEqual(self.killer.calls, [])
        with open(self.log, "a") as f:
            f.write(partial[40:] + "\n")
        self.run_wd(now=T0 + 41)
        self.assertEqual(len(self.killer.calls), 1)

    def test_stale_events_never_act(self):
        # Aunque se lean líneas nuevas, si son de hace > 15 min no se mata nada.
        self.init()
        self.write([err_line(T0 + 10 + i, "ses_old") for i in range(20)])
        self.run_wd(now=T0 + 3600)
        self.assertEqual(self.killer.calls, [])
        self.assertEqual(self.action_text(), "")


class TestRotation(Base):
    def rotate(self, lines):
        os.rename(self.log, self.log + ".1")
        self.write(lines, mode="w")

    def test_rotation_processes_new_file(self):
        self.init()
        self.write([normal_line(T0 + 10 + i, "ses_n") for i in range(200)])
        self.run_wd(now=T0 + 300)
        run2 = "beef0001"
        self.procs = [(PID + 1, T0 + 400 - 1, OPENCODE_BIN)]
        self.rotate([start_line(T0 + 400, run2)] +
                    [err_line(T0 + 410 + i, "ses_new", run=run2) for i in range(15)])
        self.assertLess(os.path.getsize(self.log), os.path.getsize(self.log + ".1"))
        self.run_wd(now=T0 + 450)
        self.assertEqual([p[0] for p in self.killer.calls], [PID + 1])

    def test_shrunk_log_does_not_reprocess_history(self):
        self.init()
        hist = [err_line(T0 + 10 + i, "ses_h") for i in range(10)]
        self.write(hist)
        self.run_wd(now=T0 + 30)
        # El log encoge (truncado y reescrito con las mismas líneas antiguas): no se
        # deben volver a contar (10 + 10 = 20 dispararía).
        with open(self.log, "w") as f:
            f.write("\n".join(hist) + "\n")
        self.run_wd(now=T0 + 31)
        self.assertEqual(self.killer.calls, [])
        self.assertEqual(self.action_text(), "")


class TestSafety(Base):
    def test_dry_run_only_logs(self):
        self.init()
        self.write([err_line(T0 + 10 + i, "ses_d") for i in range(15)])
        self.run_wd(now=T0 + 60, dry_run=True)
        self.assertEqual(self.killer.calls, [])
        txt = self.action_text()
        self.assertIn("ses_d", txt)
        self.assertIn("dry-run", txt)

    def test_never_kills_non_opencode_process(self):
        self.procs = [(PID, T0 - 1.0, "/usr/bin/python3")]
        self.init()
        self.write([err_line(T0 + 10 + i, "ses_s") for i in range(15)])
        self.run_wd(now=T0 + 60)
        self.assertEqual(self.killer.calls, [])
        self.assertIn("pid=?", self.action_text())

    def test_ambiguous_start_time_does_not_kill(self):
        self.procs = [(PID, T0 - 1.0, OPENCODE_BIN), (PID + 7, T0 - 2.0, OPENCODE_BIN)]
        self.init()
        self.write([err_line(T0 + 10 + i, "ses_s") for i in range(15)])
        self.run_wd(now=T0 + 60)
        self.assertEqual(self.killer.calls, [])

    def test_process_not_holding_log_is_not_killed(self):
        self.holds = lambda pid, path: False
        self.init()
        self.write([err_line(T0 + 10 + i, "ses_s") for i in range(15)])
        self.run_wd(now=T0 + 60)
        self.assertEqual(self.killer.calls, [])

    def test_start_time_far_from_run_is_not_matched(self):
        self.procs = [(PID, T0 - 300.0, OPENCODE_BIN)]
        self.init()
        self.write([err_line(T0 + 10 + i, "ses_s") for i in range(15)])
        self.run_wd(now=T0 + 60)
        self.assertEqual(self.killer.calls, [])


class TestParsing(unittest.TestCase):
    def test_parse_real_line(self):
        ln = ('timestamp=2026-10-17T00:31:53.254Z level=ERROR run=ca48fd62 '
              'message="stream error" providerID=llm-stack modelID=local-worker '
              'session.id=ses_xxx small=false agent=worker mode=subagent '
              'error.error="AI_APICallError: \\"quoted\\" agent=compaction"')
        f = wd.parse_line(ln)
        self.assertEqual(f["message"], "stream error")
        self.assertEqual(f["run"], "ca48fd62")
        self.assertEqual(f["session.id"], "ses_xxx")
        self.assertEqual(f["agent"], "worker")
        self.assertEqual(wd.classify(f), "err")

    def test_unterminated_quote_does_not_override_real_fields(self):
        # Línea truncada: la comilla del error no se cierra y su texto trae claves.
        ln = ('timestamp=2026-10-17T00:31:53.254Z level=ERROR run=ca48fd62 '
              'message="stream error" session.id=ses_real agent=worker '
              'error.error="boom message=stream agent=compaction session.id=ses_fake')
        f = wd.parse_line(ln)
        self.assertEqual(f["session.id"], "ses_real")
        self.assertEqual(f["agent"], "worker")
        self.assertEqual(f["message"], "stream error")
        self.assertAlmostEqual(wd.parse_ts(f["timestamp"]),
                               datetime(2026, 10, 17, 0, 31, 53, 254000,
                                        tzinfo=timezone.utc).timestamp(), places=3)


if __name__ == "__main__":
    unittest.main()
