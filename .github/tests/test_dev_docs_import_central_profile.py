"""Original required names reflect full approved central validation outcomes."""
import json
import subprocess
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).parent / 'fixtures/dev-original-docs-import-source.json'
SPECS = (
    ('rtd-sphinx-build.yml', 'rtd-sphinx-build-on-ubuntu-latest.yml',
     'sphinx', 'sphinx', 'full-original-docs'),
    ('import-smoke.yml', 'import-smoke-on-ubuntu-py3-12.yml',
     'install-check', 'import-smoke-on-ubuntu-py3-12', 'full-original-import'),
)


def sources(central, leaf):
    original = yaml.safe_load(json.loads(FIXTURE.read_text())[central]['dev']['body'])
    candidate = yaml.safe_load((ROOT / '.github/workflows' / leaf).read_text())
    return original, candidate


class TestFullCentralProfileCallers(unittest.TestCase):
    def test_every_original_event_declaration_is_preserved(self):
        observed = []
        for central, leaf, _, _, _ in SPECS:
            baseline, candidate = sources(central, leaf)
            observed.append((candidate['name'] == baseline['name'],
                             candidate.get('on', candidate.get(True)) == baseline.get('on', baseline.get(True))))
        self.assertEqual(observed, [(True, True)] * 2)

    def test_native_work_is_defined_only_in_the_two_selected_central_workflows(self):
        observed = []
        for central, leaf, bridge, _, full in SPECS:
            _, candidate = sources(central, leaf)
            call = candidate['jobs'][full]
            observed.append((set(candidate['jobs']) == {bridge, full}, call['uses'], call['with'],
                             'runs-on' not in call, 'steps' not in call,
                             candidate['jobs'][bridge]['runs-on']))
        self.assertEqual(observed, [(True, 'scitex-ai/.github/.github/workflows/' + central + '@refs/heads/main',
             {'dev_original_commands': True, 'runs_on': '["self-hosted","Linux","X64","scitex-org-cpu"]'},
             True, True, 'ubuntu-latest') for central, _, _, _, _ in SPECS])

    def test_original_required_names_depend_on_the_full_reusable_result(self):
        observed = []
        for central, leaf, bridge, required, full in SPECS:
            _, candidate = sources(central, leaf)
            job = candidate['jobs'][bridge]
            observed.append((job['name'], job['needs'], job['permissions'],
                             job['steps'][0]['env']))
        self.assertEqual(observed, [(required, full, {},
             {'FULL_RESULT': '${{ needs.' + full + '.result }}'})
             for _, _, _, required, full in SPECS])

    def test_actual_status_bridges_refuse_failure_cancel_skip_and_unknown(self):
        observed = []
        for central, leaf, bridge, _, _ in SPECS:
            _, candidate = sources(central, leaf)
            script = candidate['jobs'][bridge]['steps'][0]['run']
            for value in ('success', 'failure', 'cancelled', 'skipped', '', 'unknown'):
                child = subprocess.run(['/bin/sh', '-c', script], env={'PATH': '/usr/bin:/bin',
                    'FULL_RESULT': value}, capture_output=True, timeout=3, check=False)
                observed.append(child.returncode)
        self.assertEqual(observed, [0, 1, 1, 1, 1, 1] * 2)

    def test_docs_loop_guard_and_develop_write_authority_remain_original(self):
        baseline, candidate = sources(*SPECS[0][:2])
        original = baseline['jobs']['sphinx']
        call = candidate['jobs']['full-original-docs']
        bridge = candidate['jobs']['sphinx']
        self.assertEqual((call['if'], call['permissions'], bridge['if']),
                         (original['if'], original['permissions'], 'always() && (' + original['if'] + ')'))

    def test_import_caller_does_not_gain_a_write_permission(self):
        _, candidate = sources(*SPECS[1][:2])
        self.assertEqual(('permissions' in candidate['jobs']['full-original-import'],
                          candidate['jobs']['install-check']['if']), (False, 'always()'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
