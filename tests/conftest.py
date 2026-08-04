import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).parents[1]))
@pytest.fixture
def tmp_path():
    root=Path(__file__).parent/'runtime';root.mkdir(exist_ok=True)
    return root
