#!/bin/bash
#
# Start YouTube Transcript Daily Review Web Interface
#

cd "$(dirname "$0")"

echo "📚 Starting Reading Digest Web Interface"
echo "======================================="
echo ""

# Check if Flask is installed
if ! python3 -c "import flask" 2>/dev/null; then
    echo "❌ Flask not found. Installing..."
    pip install flask
    echo ""
fi

# Start the web interface
echo "🚀 Starting web server..."
echo "📍 Open in browser: http://localhost:5001"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

python3 app.py
