import sys 
from pathlib import Path

path = Path(__file__).resolve().parent.parent / "logic"
sys.path.insert(0, str(path))

