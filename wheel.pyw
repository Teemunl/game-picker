import pathlib
import sys

here = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(here))

import wheel

if __name__ == "__main__":
    wheel.main()
