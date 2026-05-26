"""Entry point `python -m trimtokens.gui` (lancement direct du package).

Délègue à `gui.app.main()`. Cible le launcher Windows `LanceTrim.bat` qui
exécute `python -m trimtokens.gui`.
"""

from __future__ import annotations

from trimtokens.gui.app import main

if __name__ == "__main__":
    main()
