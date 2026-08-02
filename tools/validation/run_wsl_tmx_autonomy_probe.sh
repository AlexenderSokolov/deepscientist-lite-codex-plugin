#!/usr/bin/env bash
# Create one isolated tmux owner only for the bounded WSL reconnect probe.
set -euo pipefail

if [[ $# -eq 3 && "$1" == "--reconnect" ]]; then
  socket_path="$2"
  session_name="$3"
  tmux -S "$socket_path" has-session -t "$session_name"
  printf 'RECONNECT_SERVER_PID='
  tmux -S "$socket_path" display-message -p '#{pid}'
  printf '\nRECONNECT_PANES\n'
  tmux -S "$socket_path" list-panes -t "$session_name:0" \
    -F '#{pane_index}|#{pane_id}|#{pane_pid}|#{pane_current_command}|#{pane_dead}'
  exit 0
fi

if [[ $# -ne 2 ]]; then
  printf 'usage: %s [--reconnect] <socket-path> <session-name>\n' "$0" >&2
  exit 64
fi

socket_path="$1"
session_name="$2"

if [[ -e "$socket_path" ]]; then
  printf 'refusing to reuse socket: %s\n' "$socket_path" >&2
  exit 65
fi

tmux -S "$socket_path" new-session -d -s "$session_name" -n control 'exec sleep 600'
tmux -S "$socket_path" split-window -t "$session_name:0.0" -h \
  'printf workload-ready; sleep 2; printf workload-complete; exec sleep 600'
sleep 3

printf 'SOCKET='
stat -Lc '%U:%a:%i' "$socket_path"
printf '\nSERVER_PID='
tmux -S "$socket_path" display-message -p '#{pid}'
printf '\nPANES\n'
tmux -S "$socket_path" list-panes -t "$session_name:0" \
  -F '#{pane_index}|#{pane_id}|#{pane_pid}|#{pane_current_command}|#{pane_dead}'
printf '\nBOOT_ID='
cat /proc/sys/kernel/random/boot_id
