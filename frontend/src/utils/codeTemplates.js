export const STARTER_CODE = {
  python: `def solve():
    # Write your solution here
    pass

if __name__ == "__main__":
    solve()
`,
  java: `public class Main {
    public static void main(String[] args) {
        // Write your solution here
    }
}
`,
  cpp: `#include <bits/stdc++.h>
using namespace std;

int main() {
    // Write your solution here
    return 0;
}
`,
};

export const LANGUAGE_OPTIONS = [
  { value: "python", label: "Python", monaco: "python" },
  { value: "java", label: "Java", monaco: "java" },
  { value: "cpp", label: "C++", monaco: "cpp" },
];

export function draftKey(questionId, language) {
  return `dsa-code:${questionId}:${language}`;
}
