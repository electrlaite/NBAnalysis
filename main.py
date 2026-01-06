import sys
from streamlit.web import cli as stcli

if __name__ == "__main__":
    # Ceci simule la commande "streamlit run app.py"
    sys.argv = ["streamlit", "run", "app.py"]
    sys.exit(stcli.main())