"""Command-line interface for Text-to-SQL."""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax
from rich.prompt import Prompt, Confirm
from rich import print as rprint

from src.interface import TextToSQLInterface, create_sample_database, QueryResult
from src.config import settings


console = Console()


class TextToSQLCLI:
    """Interactive CLI for Text-to-SQL interface."""

    def __init__(self, interface: Optional[TextToSQLInterface] = None):
        self.interface = interface or TextToSQLInterface()
        self.running = True

    def display_welcome(self) -> None:
        """Display welcome message."""
        console.clear()
        welcome_text = """
[bold cyan]Text-to-SQL Interface[/bold cyan]
[dim]Convert natural language to SQL queries[/dim]

[green]Commands:[/green]
  • Type a question in natural language
  • [bold]schema[/bold] - View database schema
  • [bold]tables[/bold] - List all tables
  • [bold]history[/bold] - View query history
  • [bold]stats[/bold] - View usage statistics
  • [bold]help[/bold] - Show this help
  • [bold]quit[/bold] / [bold]exit[/bold] - Exit the program
"""
        console.print(Panel(welcome_text, border_style="cyan"))

    def display_schema(self) -> None:
        """Display the database schema."""
        schema = self.interface.get_schema()

        for table_name, info in schema.items():
            table = Table(title=f"Table: {table_name}", show_header=True)
            table.add_column("Column", style="cyan")
            table.add_column("Type", style="green")
            table.add_column("Nullable", style="yellow")
            table.add_column("Primary Key", style="magenta")

            for col in info["columns"]:
                table.add_row(
                    col["name"],
                    col["type"],
                    "Yes" if col["nullable"] else "No",
                    "Yes" if col["primary_key"] else "No"
                )

            console.print(table)
            console.print()

    def display_result(self, result: QueryResult) -> None:
        """Display a query result."""
        # Display the generated SQL
        console.print("\n[bold cyan]Generated SQL:[/bold cyan]")
        syntax = Syntax(result.sql, "sql", theme="monokai", line_numbers=False)
        console.print(Panel(syntax, border_style="cyan"))

        if result.translation_result.explanation:
            console.print(f"[dim]{result.translation_result.explanation}[/dim]")

        if result.learned_correction_used:
            console.print("[green]✓ Using learned correction from previous feedback[/green]")

        # Display suggestions if available
        if result.suggestions:
            console.print("\n[yellow]Suggestions from similar past queries:[/yellow]")
            for i, suggestion in enumerate(result.suggestions, 1):
                console.print(f"  {i}. {suggestion['reason']}")
                console.print(f"     [dim]{suggestion['sql'][:80]}...[/dim]")

        # Display execution results
        if result.execution_result:
            if result.execution_result.success:
                data = result.execution_result.data
                row_count = result.execution_result.row_count

                console.print(f"\n[bold green]Results: {row_count} rows[/bold green] "
                            f"(Execution time: {result.execution_result.execution_time:.3f}s)")

                if data:
                    # Create results table
                    table = Table(show_header=True, header_style="bold magenta")
                    columns = list(data[0].keys())

                    for col in columns:
                        table.add_column(str(col))

                    for row in data[:20]:  # Limit display to 20 rows
                        table.add_row(*[str(v) if v is not None else "NULL" for v in row.values()])

                    console.print(table)

                    if len(data) > 20:
                        console.print(f"[dim]... and {len(data) - 20} more rows[/dim]")

                if result.execution_result.truncated:
                    console.print(f"[yellow]⚠ Results truncated (see security settings)[/yellow]")

                for warning in result.execution_result.security_warnings:
                    console.print(f"[yellow]⚠ {warning}[/yellow]")

            else:
                console.print(f"\n[bold red]Execution Error:[/bold red] {result.execution_result.error_message}")

        elif result.error:
            console.print(f"\n[bold red]Error:[/bold red] {result.error}")

    def prompt_feedback(self, result: QueryResult) -> None:
        """Prompt for feedback on a query."""
        if not result.success:
            return

        console.print("\n[dim]Was this result helpful?[/dim]")
        helpful = Prompt.ask(
            "Rate this query",
            choices=["y", "n", "s"],
            default="s"
        )

        if helpful == "s":  # Skip
            return

        was_helpful = helpful == "y"

        if not was_helpful:
            corrected_sql = Prompt.ask(
                "Enter corrected SQL (or press Enter to skip)",
                default=""
            )

            notes = Prompt.ask(
                "Add notes (optional)",
                default=""
            )

            self.interface.provide_feedback(
                natural_query=result.natural_query,
                original_sql=result.sql,
                corrected_sql=corrected_sql if corrected_sql else None,
                was_helpful=was_helpful,
                notes=notes
            )
            console.print("[green]Thank you! Your feedback will improve future queries.[/green]")
        else:
            self.interface.provide_feedback(
                natural_query=result.natural_query,
                original_sql=result.sql,
                was_helpful=True
            )

    def display_history(self) -> None:
        """Display query history."""
        history = self.interface.get_history(limit=10)

        if not history:
            console.print("[dim]No queries in history[/dim]")
            return

        table = Table(title="Query History", show_header=True)
        table.add_column("#", style="dim", width=3)
        table.add_column("Query", style="cyan", width=40)
        table.add_column("Status", width=10)
        table.add_column("Rows", width=6)

        for i, result in enumerate(history, 1):
            status = "[green]✓[/green]" if result.success else "[red]✗[/red]"
            rows = str(result.execution_result.row_count) if result.execution_result else "-"
            table.add_row(
                str(i),
                result.natural_query[:40] + ("..." if len(result.natural_query) > 40 else ""),
                status,
                rows
            )

        console.print(table)

    def display_stats(self) -> None:
        """Display usage statistics."""
        stats = self.interface.get_stats()

        stats_text = f"""
[bold]Usage Statistics[/bold]

[green]Queries:[/green]
  Total: {stats['queries_total']}
  Successful: {stats['queries_successful']}
  Success Rate: {stats['queries_successful'] / max(stats['queries_total'], 1) * 100:.1f}%

[green]Feedback:[/green]
  Total Entries: {stats['feedback']['total']}
  Corrections: {stats['feedback']['corrections']}
  Helpful Rate: {stats['feedback']['helpful_rate']:.1f}%

[green]Security:[/green]
  Max Rows: {stats['security']['config']['max_rows']}
  Query Timeout: {stats['security']['config']['query_timeout']}s
"""
        console.print(Panel(stats_text, border_style="green"))

    def process_query(self, query: str) -> None:
        """Process a natural language query."""
        with console.status("[bold green]Translating query...[/bold green]"):
            result = self.interface.query(query, execute=True)

        self.display_result(result)

        # Prompt for feedback if query was executed
        if result.execution_result and result.execution_result.success:
            self.prompt_feedback(result)

    def run(self) -> None:
        """Run the interactive CLI."""
        self.display_welcome()

        # Check if database is accessible
        if not self.interface.db_manager.test_connection():
            console.print("[red]Warning: Could not connect to database. Some features may not work.[/red]")

        while self.running:
            try:
                query = Prompt.ask("\n[bold cyan]Query[/bold cyan]")

                if not query.strip():
                    continue

                query_lower = query.lower().strip()

                # Handle commands
                if query_lower in ("quit", "exit", "q"):
                    self.running = False
                    console.print("[green]Goodbye![/green]")

                elif query_lower == "help":
                    self.display_welcome()

                elif query_lower == "schema":
                    self.display_schema()

                elif query_lower == "tables":
                    tables = self.interface.get_table_names()
                    console.print("[bold]Tables:[/bold] " + ", ".join(tables))

                elif query_lower == "history":
                    self.display_history()

                elif query_lower == "stats":
                    self.display_stats()

                else:
                    self.process_query(query)

            except KeyboardInterrupt:
                console.print("\n[yellow]Press Ctrl+C again or type 'quit' to exit[/yellow]")

            except Exception as e:
                console.print(f"[red]Error: {str(e)}[/red]")


def main():
    """Main entry point for CLI."""
    import argparse

    parser = argparse.ArgumentParser(description="Text-to-SQL Interface")
    parser.add_argument("--db", help="Database URL", default=None)
    parser.add_argument("--setup", action="store_true", help="Create sample database")
    parser.add_argument("--query", "-q", help="Execute a single query and exit")
    parser.add_argument("--export-feedback", help="Export feedback to file")
    parser.add_argument("--import-feedback", help="Import feedback from file")

    args = parser.parse_args()

    # Setup sample database if requested
    if args.setup:
        console.print("[cyan]Creating sample database...[/cyan]")
        create_sample_database(args.db or "./data/sample.db")
        console.print("[green]Sample database created![/green]")
        return

    # Create interface
    interface = TextToSQLInterface(database_url=args.db)

    # Export feedback
    if args.export_feedback:
        count = interface.export_feedback(args.export_feedback)
        console.print(f"[green]Exported {count} feedback entries to {args.export_feedback}[/green]")
        return

    # Import feedback
    if args.import_feedback:
        count = interface.import_feedback(args.import_feedback)
        console.print(f"[green]Imported {count} feedback entries from {args.import_feedback}[/green]")
        return

    # Single query mode
    if args.query:
        result = interface.query(args.query, execute=True)
        cli = TextToSQLCLI(interface)
        cli.display_result(result)
        return

    # Interactive mode
    cli = TextToSQLCLI(interface)
    cli.run()


if __name__ == "__main__":
    main()
