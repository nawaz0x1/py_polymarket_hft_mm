nohup in_memory_db/in_mem_db &
nohup python order_listener.py &
sudo env "PATH=$PATH" python main.py 