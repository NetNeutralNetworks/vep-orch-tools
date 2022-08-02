# this will create a tmux session and will reattatch if it allready exists
[ -z "$TMUX"  ] && { tmux send-keys /etc/profile.d/nc.sh ENTER && \
                     tmux attach || \
                     exec tmux new-session && exit; }
