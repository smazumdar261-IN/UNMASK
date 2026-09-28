"""Sample demonstrating Control-Flow Flattening and dead control-flow obfuscation."""

def execute_payload():
    # Opaque dead branch
    if 5 * 2 == 99:
        print("This is completely dead branch")
        return "DEAD"

    # Redundant empty branch with pure condition
    if 10 > 5:
        pass

    # Flattened control flow state-machine loop
    state = 1
    total = 0
    while state != 0:
        if state == 1:
            step_a = 100
            total += step_a
            state = 2
        elif state == 2:
            step_b = 200
            total += step_b
            state = 3
        elif state == 3:
            total += 50
            state = 0

    return total


if __name__ == "__main__":
    result = execute_payload()
    print("Payload result:", result)
