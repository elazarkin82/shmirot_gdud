import sys
import os

# Add src to python path to ensure imports work correctly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from shmirot_gdud.gui.app import main

if __name__ == "__main__":
    main()
