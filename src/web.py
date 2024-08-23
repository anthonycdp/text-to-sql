"""Web interface for Text-to-SQL using Flask."""

import json
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from typing import Optional

from src.interface import TextToSQLInterface, create_sample_database
from src.config import settings


# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Global interface instance
_interface: Optional[TextToSQLInterface] = None


def get_interface() -> TextToSQLInterface:
    """Get or create the interface instance."""
    global _interface
    if _interface is None:
        _interface = TextToSQLInterface()
    return _interface


# HTML Template for the web interface
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Text-to-SQL Interface</title>
    <style>
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #e0e0e0;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }

        header {
            text-align: center;
            padding: 30px 0;
        }

        h1 {
            color: #00d4ff;
            font-size: 2.5rem;
            margin-bottom: 10px;
        }

        .subtitle {
            color: #888;
            font-size: 1.1rem;
        }

        .main-content {
            display: grid;
            grid-template-columns: 1fr 300px;
            gap: 20px;
            margin-top: 20px;
        }

        @media (max-width: 900px) {
            .main-content {
                grid-template-columns: 1fr;
            }
        }

        .card {
            background: rgba(255, 255, 255, 0.05);
            border-radius: 12px;
            padding: 20px;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }

        .query-section {
            margin-bottom: 20px;
        }

        .query-input {
            width: 100%;
            padding: 15px;
            border: 2px solid #333;
            border-radius: 8px;
            background: rgba(0, 0, 0, 0.3);
            color: #fff;
            font-size: 1rem;
            resize: vertical;
            min-height: 80px;
        }

        .query-input:focus {
            outline: none;
            border-color: #00d4ff;
        }

        .button-group {
            display: flex;
            gap: 10px;
            margin-top: 15px;
        }

        button {
            padding: 12px 24px;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 1rem;
            transition: all 0.3s;
        }

        .btn-primary {
            background: linear-gradient(135deg, #00d4ff 0%, #0099cc 100%);
            color: #000;
            font-weight: 600;
        }

        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0, 212, 255, 0.3);
        }

        .btn-secondary {
            background: rgba(255, 255, 255, 0.1);
            color: #fff;
        }

        .btn-secondary:hover {
            background: rgba(255, 255, 255, 0.2);
        }

        .result-section {
            margin-top: 20px;
        }

        .sql-display {
            background: #1a1a1a;
            border-radius: 8px;
            padding: 15px;
            font-family: 'Monaco', 'Menlo', monospace;
            font-size: 0.9rem;
            overflow-x: auto;
            border-left: 3px solid #00d4ff;
        }

        .sql-keyword {
            color: #00d4ff;
            font-weight: bold;
        }

        .sql-string {
            color: #98c379;
        }

        .sql-number {
            color: #d19a66;
        }

        .results-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
            font-size: 0.9rem;
        }

        .results-table th {
            background: rgba(0, 212, 255, 0.2);
            padding: 12px;
            text-align: left;
            border-bottom: 2px solid #00d4ff;
        }

        .results-table td {
            padding: 10px 12px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        }

        .results-table tr:hover {
            background: rgba(255, 255, 255, 0.05);
        }

        .stats-badge {
            display: inline-block;
            background: rgba(0, 212, 255, 0.2);
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.85rem;
            margin-right: 10px;
        }

        .sidebar .card {
            margin-bottom: 15px;
        }

        .sidebar h3 {
            color: #00d4ff;
            margin-bottom: 15px;
            font-size: 1rem;
        }

        .schema-item {
            background: rgba(0, 0, 0, 0.2);
            padding: 10px;
            border-radius: 6px;
            margin-bottom: 8px;
        }

        .schema-item h4 {
            color: #fff;
            font-size: 0.95rem;
            margin-bottom: 5px;
        }

        .schema-item ul {
            list-style: none;
            font-size: 0.85rem;
        }

        .schema-item li {
            color: #888;
            padding: 2px 0;
        }

        .feedback-section {
            margin-top: 20px;
            padding: 15px;
            background: rgba(0, 0, 0, 0.2);
            border-radius: 8px;
        }

        .feedback-buttons {
            display: flex;
            gap: 10px;
        }

        .btn-feedback {
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 0.9rem;
        }

        .btn-helpful {
            background: rgba(76, 175, 80, 0.2);
            color: #4caf50;
            border: 1px solid #4caf50;
        }

        .btn-not-helpful {
            background: rgba(244, 67, 54, 0.2);
            color: #f44336;
            border: 1px solid #f44336;
        }

        .correction-input {
            margin-top: 10px;
        }

        .correction-input textarea {
            width: 100%;
            padding: 10px;
            border-radius: 6px;
            border: 1px solid #333;
            background: rgba(0, 0, 0, 0.3);
            color: #fff;
            font-family: monospace;
        }

        .error-message {
            background: rgba(244, 67, 54, 0.1);
            border-left: 3px solid #f44336;
            padding: 15px;
            border-radius: 0 8px 8px 0;
            margin-top: 15px;
        }

        .success-message {
            background: rgba(76, 175, 80, 0.1);
            border-left: 3px solid #4caf50;
            padding: 15px;
            border-radius: 0 8px 8px 0;
            margin-top: 15px;
        }

        .loading {
            display: none;
            text-align: center;
            padding: 20px;
        }

        .loading.active {
            display: block;
        }

        .spinner {
            border: 3px solid rgba(255, 255, 255, 0.1);
            border-top-color: #00d4ff;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            animation: spin 1s linear infinite;
            margin: 0 auto;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        .hidden {
            display: none;
        }

        footer {
            text-align: center;
            padding: 30px;
            color: #666;
            font-size: 0.9rem;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Text-to-SQL Interface</h1>
            <p class="subtitle">Convert natural language queries to SQL</p>
        </header>

        <div class="main-content">
            <div class="content">
                <div class="card query-section">
                    <textarea id="queryInput" class="query-input"
                        placeholder="Ask a question in natural language...&#10;&#10;Examples:&#10;- Show all employees in Engineering&#10;- What is the average salary by department?&#10;- List the top 5 products by price"></textarea>
                    <div class="button-group">
                        <button class="btn-primary" onclick="executeQuery()">Execute Query</button>
                        <button class="btn-secondary" onclick="clearResults()">Clear</button>
                    </div>
                </div>

                <div class="loading" id="loading">
                    <div class="spinner"></div>
                    <p>Processing query...</p>
                </div>

                <div id="resultsSection" class="card result-section hidden">
                    <div id="sqlDisplay" class="sql-display"></div>
                    <div id="resultStats" style="margin-top: 10px;"></div>
                    <div id="resultsTable"></div>

                    <div class="feedback-section" id="feedbackSection">
                        <p>Was this result helpful?</p>
                        <div class="feedback-buttons">
                            <button class="btn-feedback btn-helpful" onclick="submitFeedback(true)">👍 Helpful</button>
                            <button class="btn-feedback btn-not-helpful" onclick="showCorrectionForm()">👎 Not Helpful</button>
                        </div>
                        <div id="correctionForm" class="correction-input hidden">
                            <textarea id="correctionSql" placeholder="Enter corrected SQL..."></textarea>
                            <input type="text" id="correctionNotes" placeholder="Notes (optional)"
                                style="width: 100%; margin-top: 10px; padding: 10px; border-radius: 6px; border: 1px solid #333; background: rgba(0,0,0,0.3); color: #fff;">
                            <button class="btn-primary" style="margin-top: 10px;" onclick="submitFeedback(false)">Submit Correction</button>
                        </div>
                    </div>
                </div>

                <div id="errorSection" class="error-message hidden"></div>
            </div>

            <div class="sidebar">
                <div class="card">
                    <h3>📊 Statistics</h3>
                    <div id="statsDisplay"></div>
                </div>

                <div class="card">
                    <h3>📋 Schema</h3>
                    <div id="schemaDisplay"></div>
                </div>

                <div class="card">
                    <h3>💡 Example Queries</h3>
                    <ul style="list-style: none;">
                        <li style="padding: 8px 0; cursor: pointer;" onclick="setQuery('Show all employees')">
                            Show all employees
                        </li>
                        <li style="padding: 8px 0; cursor: pointer;" onclick="setQuery('What is the average salary by department?')">
                            Average salary by department
                        </li>
                        <li style="padding: 8px 0; cursor: pointer;" onclick="setQuery('List the top 5 products by price')">
                            Top 5 products by price
                        </li>
                        <li style="padding: 8px 0; cursor: pointer;" onclick="setQuery('Count employees in each department')">
                            Count employees by department
                        </li>
                        <li style="padding: 8px 0; cursor: pointer;" onclick="setQuery('Show total sales by region')">
                            Total sales by region
                        </li>
                    </ul>
                </div>
            </div>
        </div>

        <footer>
            Text-to-SQL Interface • Built with Python & LangChain
        </footer>
    </div>

    <script>
        let currentQuery = '';
        let currentSql = '';

        // Initialize
        document.addEventListener('DOMContentLoaded', () => {
            loadStats();
            loadSchema();
        });

        async function executeQuery() {
            const query = document.getElementById('queryInput').value.trim();
            if (!query) return;

            currentQuery = query;
            showLoading(true);
            hideError();
            hideResults();

            try {
                const response = await fetch('/api/query', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ query })
                });

                const data = await response.json();

                if (data.success) {
                    currentSql = data.sql;
                    displayResults(data);
                } else {
                    showError(data.error || 'An error occurred');
                }
            } catch (error) {
                showError('Failed to execute query: ' + error.message);
            } finally {
                showLoading(false);
            }
        }

        function displayResults(data) {
            document.getElementById('resultsSection').classList.remove('hidden');

            // Display SQL
            document.getElementById('sqlDisplay').innerHTML = highlightSQL(data.sql);

            // Display stats
            const statsHtml = `
                <span class="stats-badge">${data.row_count || 0} rows</span>
                <span class="stats-badge">${data.execution_time?.toFixed(3) || 0}s</span>
                ${data.learned_correction ? '<span class="stats-badge">📚 Learned</span>' : ''}
            `;
            document.getElementById('resultStats').innerHTML = statsHtml;

            // Display results table
            if (data.data && data.data.length > 0) {
                const columns = Object.keys(data.data[0]);
                let tableHtml = '<table class="results-table"><thead><tr>';
                columns.forEach(col => {
                    tableHtml += `<th>${col}</th>`;
                });
                tableHtml += '</tr></thead><tbody>';

                data.data.forEach(row => {
                    tableHtml += '<tr>';
                    columns.forEach(col => {
                        tableHtml += `<td>${row[col] !== null ? row[col] : '<i>NULL</i>'}</td>`;
                    });
                    tableHtml += '</tr>';
                });

                tableHtml += '</tbody></table>';
                document.getElementById('resultsTable').innerHTML = tableHtml;
            } else {
                document.getElementById('resultsTable').innerHTML = '<p style="color: #888; margin-top: 10px;">No results found</p>';
            }
        }

        function highlightSQL(sql) {
            if (!sql) return '';
            const keywords = ['SELECT', 'FROM', 'WHERE', 'JOIN', 'LEFT', 'RIGHT', 'INNER', 'ON', 'AND', 'OR', 'GROUP BY', 'ORDER BY', 'LIMIT', 'AS', 'COUNT', 'SUM', 'AVG', 'MAX', 'MIN', 'HAVING', 'DISTINCT', 'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'DROP', 'ALTER', 'TABLE', 'INDEX', 'NULL', 'NOT', 'TRUE', 'FALSE'];
            let highlighted = sql;
            keywords.forEach(keyword => {
                const regex = new RegExp(`\\b${keyword}\\b`, 'gi');
                highlighted = highlighted.replace(regex, `<span class="sql-keyword">${keyword}</span>`);
            });
            return highlighted;
        }

        async function submitFeedback(helpful) {
            const correction = document.getElementById('correctionSql').value;
            const notes = document.getElementById('correctionNotes').value;

            try {
                await fetch('/api/feedback', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        query: currentQuery,
                        sql: currentSql,
                        helpful: helpful,
                        correction: correction,
                        notes: notes
                    })
                });

                alert('Thank you for your feedback!');
                document.getElementById('feedbackSection').classList.add('hidden');
                loadStats();
            } catch (error) {
                console.error('Failed to submit feedback:', error);
            }
        }

        function showCorrectionForm() {
            document.getElementById('correctionForm').classList.remove('hidden');
        }

        async function loadStats() {
            try {
                const response = await fetch('/api/stats');
                const stats = await response.json();

                document.getElementById('statsDisplay').innerHTML = `
                    <p>Queries: ${stats.queries_total || 0}</p>
                    <p>Successful: ${stats.queries_successful || 0}</p>
                    <p>Corrections: ${stats.feedback?.corrections || 0}</p>
                `;
            } catch (error) {
                console.error('Failed to load stats:', error);
            }
        }

        async function loadSchema() {
            try {
                const response = await fetch('/api/schema');
                const schema = await response.json();

                let html = '';
                for (const [table, info] of Object.entries(schema)) {
                    html += `<div class="schema-item">
                        <h4>${table}</h4>
                        <ul>
                            ${info.columns.slice(0, 5).map(col => `<li>${col.name} (${col.type})</li>`).join('')}
                            ${info.columns.length > 5 ? `<li>... and ${info.columns.length - 5} more</li>` : ''}
                        </ul>
                    </div>`;
                }

                document.getElementById('schemaDisplay').innerHTML = html;
            } catch (error) {
                console.error('Failed to load schema:', error);
            }
        }

        function setQuery(query) {
            document.getElementById('queryInput').value = query;
        }

        function showLoading(show) {
            document.getElementById('loading').classList.toggle('active', show);
        }

        function hideResults() {
            document.getElementById('resultsSection').classList.add('hidden');
        }

        function showError(message) {
            document.getElementById('errorSection').textContent = message;
            document.getElementById('errorSection').classList.remove('hidden');
        }

        function hideError() {
            document.getElementById('errorSection').classList.add('hidden');
        }

        function clearResults() {
            document.getElementById('queryInput').value = '';
            hideResults();
            hideError();
            document.getElementById('feedbackSection').classList.remove('hidden');
            document.getElementById('correctionForm').classList.add('hidden');
        }

        // Handle Enter key
        document.getElementById('queryInput').addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && e.ctrlKey) {
                executeQuery();
            }
        });
    </script>
</body>
</html>
"""


@app.route('/')
def index():
    """Serve the main web interface."""
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/query', methods=['POST'])
def api_query():
    """Process a natural language query."""
    data = request.get_json()
    query = data.get('query', '')

    if not query:
        return jsonify({'success': False, 'error': 'No query provided'})

    interface = get_interface()
    result = interface.query(query, execute=True)

    response = {
        'success': result.success,
        'query': result.natural_query,
        'sql': result.sql,
        'explanation': result.translation_result.explanation,
        'learned_correction': result.learned_correction_used,
        'error': result.error,
    }

    if result.execution_result:
        response['data'] = result.execution_result.data
        response['row_count'] = result.execution_result.row_count
        response['execution_time'] = result.execution_result.execution_time
        response['truncated'] = result.execution_result.truncated
        response['warnings'] = result.execution_result.security_warnings

    return jsonify(response)


@app.route('/api/feedback', methods=['POST'])
def api_feedback():
    """Submit feedback on a query."""
    data = request.get_json()

    interface = get_interface()
    interface.provide_feedback(
        natural_query=data.get('query', ''),
        original_sql=data.get('sql', ''),
        corrected_sql=data.get('correction') if data.get('correction') else None,
        was_helpful=data.get('helpful', True),
        notes=data.get('notes', '')
    )

    return jsonify({'success': True})


@app.route('/api/schema', methods=['GET'])
def api_schema():
    """Get the database schema."""
    interface = get_interface()
    return jsonify(interface.get_schema())


@app.route('/api/stats', methods=['GET'])
def api_stats():
    """Get usage statistics."""
    interface = get_interface()
    return jsonify(interface.get_stats())


@app.route('/api/tables', methods=['GET'])
def api_tables():
    """Get list of tables."""
    interface = get_interface()
    return jsonify(interface.get_table_names())


@app.route('/api/execute', methods=['POST'])
def api_execute():
    """Execute raw SQL (with security checks)."""
    data = request.get_json()
    sql = data.get('sql', '')

    if not sql:
        return jsonify({'success': False, 'error': 'No SQL provided'})

    interface = get_interface()
    result = interface.execute_sql(sql)

    return jsonify({
        'success': result.success,
        'data': result.data,
        'row_count': result.row_count,
        'execution_time': result.execution_time,
        'error': result.error_message,
        'warnings': result.security_warnings,
    })


def run_server(host: str = '0.0.0.0', port: int = 5000, debug: bool = False):
    """Run the Flask server."""
    print(f"Starting Text-to-SQL Web Interface on http://{host}:{port}")
    app.run(host=host, port=port, debug=debug)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Text-to-SQL Web Interface')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--port', type=int, default=5000, help='Port to bind to')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    parser.add_argument('--setup', action='store_true', help='Create sample database first')

    args = parser.parse_args()

    if args.setup:
        print("Creating sample database...")
        create_sample_database()

    run_server(host=args.host, port=args.port, debug=args.debug)
