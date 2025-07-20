git pull && cp db.bak.sqlite3 db.sqlite3 && tmux new-session \; split-window -h \; send-keys '\''./runserver.sh'\'' C-m \; select-pane -L \; send-keys '\''python manage.py runserver'\'' C-m \;
