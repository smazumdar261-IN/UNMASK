def greeting(name: str) -> str:
    message = "Hello, " + name + "!"
    return message


if __name__ == "__main__":
    result = greeting("World")
    print(result)
