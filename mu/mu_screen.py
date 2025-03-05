import os
import subprocess
import sys

SCREEN_SESSION = 'mu_session'


def get_project_dir():
    """
    Determine the project root directory.
    - If run as a package (e.g., `mu.mu_screen`), use the installed location.
    - If run as a standalone script, use the script's directory.
    """
    if __name__.startswith('mu.'):
        import mu
        return os.path.abspath(os.path.dirname(mu.__file__))
    else:
        return os.path.abspath(os.path.dirname(__file__))


def is_screen_installed():
    """Check if 'screen' is installed on the system."""
    return os.system('which screen > /dev/null 2>&1') == 0


def screen_session_exists():
    """Check if a screen session already exists."""
    result = subprocess.run(['screen', '-ls'], capture_output=True, text=True)
    return SCREEN_SESSION in result.stdout


def main():
    if not is_screen_installed():
        print("Error: 'screen' is not installed.", file=sys.stderr)
        sys.exit(1)

    project_dir = get_project_dir()  # Get the correct project directory
    mu_script = os.path.join(project_dir, 'main.py')  # Path to main.py
    args = ' '.join(f'"{arg}"' for arg in sys.argv[1:])

    if not screen_session_exists():
        subprocess.run([
            'screen', '-S', SCREEN_SESSION, '-d', '-m', 'bash', '-c',
            f"python3 {mu_script} {args}; "
            f"echo '\n\033[1;33mWARNING: You are still inside the screen session! Press Ctrl+A, then D to detach or Ctrl+d to terminate the screen session.\033[0m'; "  # noqa: E501
            f"exec bash",
        ])

    # Attach to the screen session
    os.execvp('screen', ['screen', '-r', SCREEN_SESSION])


if __name__ == '__main__':
    raise SystemExit(main())
