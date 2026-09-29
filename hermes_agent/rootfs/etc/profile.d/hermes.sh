# Shell interattive dell'utente hermes (sessioni SSH).
case $- in *i*) ;; *) return ;; esac
cd /data/hermes 2>/dev/null || true
echo ""
echo "  Hermes Agent - CLI"
echo "    hermes model     scegli provider e modello"
echo "    hermes setup     configurazione guidata"
echo "    hermes chat      chat da terminale"
echo "    hermes doctor    diagnostica"
echo ""
