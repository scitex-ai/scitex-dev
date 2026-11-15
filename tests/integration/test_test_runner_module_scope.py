"""Explicit local module requests must never broaden into the whole suite."""
import os
import subprocess
import sys

import pytest
from scitex_dev.test_runner import TestConfig as RunnerConfig, _build_pytest_args


LAYOUTS={'legacy':'scitex/alpha','direct':'alpha','qualified':'scitex_dev/alpha'}


def create_project(directory, layout='direct', *, failure=False):
    initialize_project(directory)
    module=LAYOUTS[layout];selected=directory/'tests'/module;other=directory/'tests/other'
    selected.mkdir(parents=True);other.mkdir(parents=True)
    body="raise AssertionError('intentional local runner fixture failure')" if failure else "Path("+repr(str(directory/'selected.marker'))+").write_text('selected')"
    (selected/'test_selected.py').write_text('from pathlib import Path\ndef test_selected():\n    '+body+'\n')
    (other/'test_other.py').write_text('from pathlib import Path\ndef test_other():\n    Path('+repr(str(directory/'other.marker'))+").write_text('other')\n")
    (directory/'pytest.ini').write_text('[pytest]\n')
    return module,selected


def invoke_local(directory, module):
    code='import sys\nfrom scitex_dev.test_runner import TestConfig,run_local\nsys.exit(run_local(TestConfig(module='+repr(module)+",parallel='0')))\n"
    return subprocess.run([sys.executable,'-c',code],cwd=directory,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),capture_output=True,text=True,timeout=30)


@pytest.mark.parametrize('layout',['legacy','direct','qualified','no_tests'])
def test_missing_explicit_module_returns_pytest_error_without_running_other_tests(tmp_path, layout):
    # Arrange
    prepare_missing(tmp_path,layout)
    # Act
    result=invoke_local(tmp_path,'does_not_exist')
    # Assert
    assert (result.returncode,(tmp_path/'selected.marker').exists(),(tmp_path/'other.marker').exists(),'does_not_exist' in result.stderr) == (4,False,False,True)


def initialize_project(directory):
    subprocess.run(['git','init','--quiet',str(directory)],capture_output=True,text=True,check=True,timeout=10)


def prepare_missing(directory, layout):
    if layout=='no_tests':
        initialize_project(directory)
    else:
        create_project(directory,layout)


@pytest.mark.parametrize('layout',['legacy','direct','qualified'])
def test_existing_module_selects_only_its_real_tests(tmp_path, layout):
    # Arrange
    module,selected=create_project(tmp_path,layout)
    # Act
    result=invoke_local(tmp_path,module)
    # Assert
    assert (result.returncode,(tmp_path/'selected.marker').read_text(),(tmp_path/'other.marker').exists()) == (0,'selected',False)


def test_empty_module_keeps_intentional_whole_suite_selection(tmp_path):
    # Arrange
    create_project(tmp_path)
    # Act
    result=invoke_local(tmp_path,'')
    # Assert
    assert (result.returncode,(tmp_path/'selected.marker').read_text(),(tmp_path/'other.marker').read_text()) == (0,'selected','other')


def test_valid_module_preserves_real_pytest_failure_exit_code(tmp_path):
    # Arrange
    module,selected=create_project(tmp_path,failure=True)
    # Act
    result=invoke_local(tmp_path,module)
    # Assert
    assert (result.returncode,'intentional local runner fixture failure' in result.stdout,(tmp_path/'other.marker').exists()) == (1,True,False)


def test_legacy_directory_precedence_is_preserved(tmp_path):
    # Arrange
    module,selected=create_project(tmp_path,'legacy');direct=tmp_path/'tests/alpha';direct.mkdir();(direct/'test_direct.py').write_text("def test_direct():\n    raise AssertionError('wrong module directory selected')\n")
    # Act
    result=invoke_local(tmp_path,'alpha')
    # Assert
    assert (result.returncode,(tmp_path/'selected.marker').read_text(),(tmp_path/'other.marker').exists()) == (0,'selected',False)


def test_existing_pytest_option_forwarding_is_preserved(tmp_path):
    # Arrange
    module,selected=create_project(tmp_path);config=RunnerConfig(module=module,parallel='2',fast=True,coverage=True,exitfirst=True,pattern='selection',changed=True,last_failed=True)
    # Act
    result=_build_pytest_args(config,str(tmp_path))
    # Assert
    assert result == [sys.executable,'-m','pytest',str(selected),'-n','2','--dist','loadfile','-m','not slow','-x','-k','selection','--lf','--testmon','--cov','--cov-report=term-missing','--tb=short']
