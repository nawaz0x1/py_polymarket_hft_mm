nohup in_memory_db/in_mem_db &
nohup order_listener.py &
sudo env "PATH=$PATH" python main.py 