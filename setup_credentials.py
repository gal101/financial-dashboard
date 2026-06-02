import os

def main():
    print("Tradeville API Credentials Setup")
    user = input("Enter TRADEVILLE_USER [!DemoAPITDV]: ").strip()
    if not user:
        user = "!DemoAPITDV"
        
    password = input("Enter TRADEVILLE_PASSWORD [DemoAPITDV]: ").strip()
    if not password:
        password = "DemoAPITDV"
        
    demo_input = input("Enter TRADEVILLE_DEMO (true/false) [true]: ").strip().lower()
    if not demo_input:
        demo = "true"
    elif demo_input in ("false", "f", "0", "n", "no"):
        demo = "false"
    else:
        demo = "true"
        
    env_content = f"""TRADEVILLE_USER={user}
TRADEVILLE_PASSWORD={password}
TRADEVILLE_DEMO={demo}
"""
    
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    with open(env_path, "w") as f:
        f.write(env_content)
        
    print(f"Credentials written successfully to {env_path}")

if __name__ == "__main__":
    main()
