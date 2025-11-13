#!/bin/bash
# Install git hooks for this repository

echo "Installing git hooks..."

# Create pre-commit hook
cat > .git/hooks/pre-commit << 'EOF'
#!/bin/bash
# Pre-commit hook to run linting checks

# Change to repository root
cd "$(git rev-parse --show-toplevel)" || exit 1

# Run lint script
./lint.sh

# Exit with the same code as lint.sh
exit $?
EOF

chmod +x .git/hooks/pre-commit

echo "✓ Pre-commit hook installed"
echo ""
echo "The hook will run lint.sh before each commit."
echo "To skip the hook temporarily, use: git commit --no-verify"
