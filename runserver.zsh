tmux new-session \; split-window -h \; send-keys '\''./runserver.sh'\'' C-m \; select-pane -L \; send-keys '\''python manage.py runserver'\'' C-m \;
