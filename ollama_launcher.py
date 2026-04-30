import subprocess

def launch_ollama():
    command = [
        "aider",
        "--model",
        "ollama_chat/qwen2.5-coder:14b-64k",
        "--map-tokens",
        "4096"
    ]
    
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as e:
        print(f"An error occurred while launching Ollama: {e}")

if __name__ == "__main__":
    launch_ollama()
