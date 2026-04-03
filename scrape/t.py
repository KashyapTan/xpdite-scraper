from typing import List
from collections import deque

def exist(board: List[List[str]], word: str) -> bool:
    directions = [(1, 0), (0, 1), (-1, 0), (0, -1)]
    rows, cols = len(board), len(board[0])

    def bfs(row, col):
        print(f"Starting BFS from ({row}, {col})")
        queue, visited = deque([(row, col)]), set()
        visited.add((row, col))
        index = 1  # Track the current index of the word being matched

        while queue:
            for _ in range(len(queue)):
                row, col = queue.popleft()
                print(f"Processing cell ({row}, {col}) with letter '{board[row][col]}'")
                if index == len(word):  # If all letters are matched
                    print("Word found!")
                    return True
                for dr, dc in directions:
                    r, c = row + dr, col + dc
                    if (
                        0 <= r < rows and
                        0 <= c < cols and
                        (r, c) not in visited and
                        board[r][c] == word[index]
                    ):
                        print(f"Adding cell ({r}, {c}) with letter '{board[r][c]}' to queue")
                        visited.add((r, c))
                        queue.append((r, c))
            index += 1  # Move to the next letter in the word
        print("BFS complete, word not found.")
        return False

    for r in range(rows):
        for c in range(cols):
            if board[r][c] == word[0]:
                print(f"Starting point found at ({r}, {c})")
                if bfs(r, c):
                    return True
    print("Word not found in the board.")
    return False

if __name__ == "__main__":
    board = [["A", "B", "C", "E"], ["S", "F", "C", "S"], ["A", "D", "E", "E"]]
    word = "ABCCED"
    print(exist(board, word))  # Output: True