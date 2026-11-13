"""Original status bridges and the published nested docs permission contract.

The historical fixture retains the original commands and loop guard. The newer
published provider snapshot binds the nested publisher requirement separately:
GitHub validates its permission ceiling even when that job will not run. These
source controls do not simulate GitHub authorization or publish a docs bundle.
"""
import hashlib
import json
import subprocess
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).parent / 'fixtures/dev-original-docs-import-source.json'
DOCS_REVISION = 'c5acd551f050094dbca4d1c3a889a08212bcd73b'
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
        expected = []
        for central, _, _, _, _ in SPECS:
            options = {'dev_original_commands': True,
                       'runs_on': '["self-hosted","Linux","X64","scitex-org-cpu"]'}
            revision = 'main'
            if central == 'rtd-sphinx-build.yml':
                revision = DOCS_REVISION
                options['bundle_dir'] = 'src/scitex_dev/_sphinx_html'
            expected.append((True, 'scitex-ai/.github/.github/workflows/'
                             + central + '@' + revision, options,
                             True, True, 'ubuntu-latest'))
        self.assertEqual(observed, expected)

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

    def test_docs_original_and_bridge_loop_guards_remain_original(self):
        baseline, candidate = sources(*SPECS[0][:2])
        original = baseline['jobs']['sphinx']
        call = candidate['jobs']['full-original-docs']
        bridge = candidate['jobs']['sphinx']
        self.assertEqual((call['if'], bridge['if']),
                         (original['if'], 'always() && (' + original['if'] + ')'))

    def test_published_provider_snapshot_has_exact_source_binding(self):
        # Arrange
        snapshot = json.loads((FIXTURE.parent / 'dev-docs-publisher-source.json').read_text())
        body = snapshot['source'].encode()
        # Act
        observed = (snapshot['repository'], snapshot['revision'], snapshot['path'],
                    len(body), hashlib.sha256(body).hexdigest(),
                    hashlib.sha1(b'blob ' + str(len(body)).encode() + b'\0' + body).hexdigest())
        # Assert
        self.assertEqual(observed, ('scitex-ai/.github',
                         '2baf2bd25f08ff0968991d1bae65ceba2e8b5b0d',
                         '.github/workflows/rtd-sphinx-build.yml', snapshot['bytes'],
                         'f7536adfb98bb9cb9862815d52b3d049f9c3032a4197a745f75bd62be5d7fa7e',
                         'c25dedf1388bcc11da07cd56029a5f37ecf416f3'))

    def test_original_docs_job_keeps_its_contents_only_write_scope(self):
        # Arrange
        baseline, _ = sources(*SPECS[0][:2])
        provider = json.loads((FIXTURE.parent / 'dev-docs-publisher-source.json').read_text())
        # Act
        observed = yaml.safe_load(provider['source'])['jobs']['dev-original-sphinx']['permissions']
        # Assert
        self.assertEqual((observed, baseline['jobs']['sphinx']['permissions']),
                         ({'contents': 'write'}, {'contents': 'write'}))

    def test_nested_publisher_requires_exact_caller_permission_union(self):
        # Arrange
        _, candidate = sources(*SPECS[0][:2])
        snapshot = json.loads((FIXTURE.parent / 'dev-docs-publisher-source.json').read_text())
        publisher = yaml.safe_load(snapshot['source'])['jobs']['publish-sphinx-bundle']
        # Act
        observed = (candidate['jobs']['full-original-docs']['permissions'],
                    publisher['permissions'], publisher['if'])
        # Assert
        self.assertEqual(observed, ({'contents': 'write', 'pull-requests': 'write'},
                         {'contents': 'write', 'pull-requests': 'write'},
                         "${{ inputs.bundle_dir != '' && github.event_name == 'push' }}"))

    def test_import_caller_does_not_gain_a_write_permission(self):
        _, candidate = sources(*SPECS[1][:2])
        self.assertEqual(('permissions' in candidate['jobs']['full-original-import'],
                          candidate['jobs']['install-check']['if']), (False, 'always()'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
