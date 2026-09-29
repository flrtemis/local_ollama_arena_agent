import argparse

def fibonacci(n):
    if n <= 0:
        return []
    elif n == 1:
        return [0]
    
    sequence = [0, 1]
    while len(sequence) < n:
        sequence.append(sequence[-1] + sequence[-2])
    return sequence

def main():
    parser = argparse.ArgumentParser(description="Generate Fibonacci sequence up to n terms.")
    parser.add_argument("n", type=int, help="Number of terms to generate")
    args = parser.parse_args()

    if args.n < 0:
        print("Please enter a non-negative integer.")
        return

    result = fibonacci(args.n)
    print(f"Fibonacci sequence ({args.n} terms): {result}")

if __name__ == "__main__":
    main()
