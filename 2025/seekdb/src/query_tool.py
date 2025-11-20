#!/usr/bin/env python3
"""
Interactive query tool for SeekDB vector database.
Allows users to perform semantic search queries on the tourism collection.
"""

import sys
import os
import traceback
import argparse
import logging
import itertools
import pyseekdb
from pyseekdb.client import DefaultEmbeddingFunction
from typing import Tuple, List, Dict, Any, Optional, Union
from enum import Enum
from pathlib import Path

# Import rich for beautiful CLI - required dependency
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich import box
except ImportError:
    print("Error: The 'rich' library is required but not installed.")
    print("Please install it with: pip install rich")
    sys.exit(1)

# Try to import readline for command history (Unix/Linux/Mac)
# On Windows, pyreadline can be used but we'll handle gracefully if not available
try:
    import readline
    READLINE_AVAILABLE = True
except ImportError:
    try:
        import pyreadline3 as readline
        READLINE_AVAILABLE = True
    except ImportError:
        READLINE_AVAILABLE = False


# Handle both relative and absolute imports
try:
    from .meta_info import MetaInfo, ClientSettings
except ImportError:
    from meta_info import MetaInfo, ClientSettings

_logger = logging.getLogger(__name__)


def _print_exception(e: Exception, console: Optional[Console] = None):
    if console:
        console.print(f"[bold red]Error:[/bold red] {e}")
        console.print_exception()
    else:
        print(f"Error: {e}")
        traceback.print_exc()

class Comparison(Enum):
    INVALID = 'INVALID'
    GREATER_THAN = '>'
    GREATER_THAN_OR_EQUAL = '>='
    LESS_THAN = '<'
    LESS_THAN_OR_EQUAL = '<='
    EQUAL = '='
    NOT_EQUAL = '!='
class ComparisonOperator:
    """Comparison operator for hybrid search."""
    def __init__(self, comparison: Comparison):
        self.comparison = comparison
    def to_query_string(self):
        if self.comparison == Comparison.GREATER_THAN_OR_EQUAL:
            return "$gte"
        elif self.comparison == Comparison.LESS_THAN_OR_EQUAL:
            return "$lte"
        elif self.comparison == Comparison.NOT_EQUAL:
            return "$ne"
        elif self.comparison == Comparison.EQUAL:
            return "$eq"
        elif self.comparison == Comparison.GREATER_THAN:
            return "$gt"
        elif self.comparison == Comparison.LESS_THAN:
            return "$lt"
        else:
            raise ValueError(f"Invalid comparison: {self.comparison}")
    @staticmethod
    def parse_operator(arg: str) -> ('ComparisonOperator', int):
        if arg.startswith('>='):
            return (ComparisonOperator(Comparison.GREATER_THAN_OR_EQUAL), 2)
        elif arg.startswith('<='):
            return (ComparisonOperator(Comparison.LESS_THAN_OR_EQUAL), 2)
        elif arg.startswith('!='):
            return (ComparisonOperator(Comparison.NOT_EQUAL), 2)
        elif arg.startswith('<>'):
            return (ComparisonOperator(Comparison.NOT_EQUAL), 2)
        elif arg.startswith('=='):
            return (ComparisonOperator(Comparison.EQUAL), 2)
        elif arg.startswith('<'):
            return (ComparisonOperator(Comparison.LESS_THAN), 1)
        elif arg.startswith('>'):
            return (ComparisonOperator(Comparison.GREATER_THAN), 1)
        else:
            return (ComparisonOperator(Comparison.INVALID), 0)
class HeightCondition:
    """Height condition for hybrid search."""
    def __init__(self, comparison: ComparisonOperator, height: int):
        self.comparison = comparison
        self.height = height
    def to_query_string(self):
        return {"height": {self.comparison.to_query_string(): self.height}}
    @staticmethod
    def parse_condition(arg: str) -> Union['HeightCondition', None]:
        arg = arg[len('height'):]
        comparison_operator, comparison_len = ComparisonOperator.parse_operator(arg)
        if comparison_operator == Comparison.INVALID or comparison_len == 0:
            return None
        value = arg[comparison_len:]
        try:
            height = float(value)
            return HeightCondition(comparison_operator, height)
        except ValueError:
            return None


class QueryTool:
    """Interactive query tool for vector database."""

    def __init__(self, client_settings, collection_name, embedding_model_name, top_k=5):
        """
        Initialize the query tool.

        Args:
            client_settings: ClientSettings object with database connection info
            collection_name: Name of the collection to query
            embedding_model_name: Name of the embedding model to use
            top_k: Number of results to return per query
        """
        self.client_settings = client_settings
        self.collection_name = collection_name
        self.embedding_model_name = embedding_model_name
        self.top_k = top_k
        self.history_file = None
        self.console = Console()
        self.client = None
        self.collection = None
        self._ensure_connection(silent=False)

    def _setup_readline_history(self):
        """Set up readline history support."""
        if not READLINE_AVAILABLE:
            return

        try:
            # Set history file path in user's home directory
            history_dir = Path.home() / '.seekdb'
            history_dir.mkdir(exist_ok=True)
            self.history_file = history_dir / 'query_history.txt'

            # Set up readline options
            readline.set_history_length(1000)  # Keep last 1000 commands

            # Load history if file exists
            if self.history_file.exists():
                try:
                    readline.read_history_file(str(self.history_file))
                except Exception as e:
                    _logger.debug(f"Could not load history: {e}")

            # Set up tab completion (optional - can be enhanced later)
            readline.parse_and_bind("tab: complete")

        except Exception as e:
            _logger.debug(f"Could not set up readline history: {e}")
            self.history_file = None

    def _save_history(self):
        """Save command history to file."""
        if not READLINE_AVAILABLE or not self.history_file:
            return

        try:
            readline.write_history_file(str(self.history_file))
        except Exception as e:
            _logger.debug(f"Could not save history: {e}")

    def _ensure_connection(self, silent: bool = False):
        # Initialize client
        # Use server mode if host is provided, otherwise use embedded mode
        need_reconnect = False
        if not self.client:
            need_reconnect = True
        try:
            self.client.count_collection()
        except Exception as e:
            _logger.debug(f"Connection is lost: {e}")
            need_reconnect = True
        if not need_reconnect:
            _logger.debug(f"Connection is still valid")
            return

        if not silent:
            self.console.print("[bold green]Initializing client...[/bold green]")
        if self.client_settings.host:
            self.client = pyseekdb.Client(
                host=self.client_settings.host,
                port=self.client_settings.port,
                user=self.client_settings.user,
                password=self.client_settings.password,
                database=self.client_settings.database
            )
        else:
            self.client = pyseekdb.Client(
                path=self.client_settings.path,
                database=self.client_settings.database
            )
        # Get collection
        if not self.client.has_collection(self.collection_name):
            raise ValueError(f"Collection '{self.collection_name}' does not exist!")
        self.collection = self.client.get_collection(self.collection_name, embedding_function=DefaultEmbeddingFunction(model_name=self.embedding_model_name))
        if not silent:
            self.console.print(f"[bold green]✓[/bold green] Connected to collection: [cyan]{self.collection_name}[/cyan]")

    def list_items(self) -> Dict[str, List[Any]]:
        """
        List the collection.
        """
        self._ensure_connection(silent=True)
        results = self.collection.get(where={"name": {"$ne":""}}, include=['metadatas'])
        return results
    def get(self, tourism_names: List[str], places: List[str]) -> List[Dict[str, Any]]:
        """
        Get the tourism information from the collection.

        Args:
            tourism_names: List of tourism names to get
            places: List of places to get
        """
        condition = []
        if tourism_names:
            condition.append({"name": {"$in": tourism_names}})
        if places:
            condition.append({"place": {"$in": places}})
        if len(condition) > 1:
            where = {"$or": condition}
        elif len(condition) == 1:
            where = condition[0]
        else:
            print("No condition provided")
            return []
        _logger.debug(f'collection.get with where: {where}')
        self._ensure_connection(silent=True)
        results = self.collection.get(where=where)
        return results
    def query_documents(self, keywords: List[str]) -> List[Dict[str, Any]]:
        """
        Query the collection by keywords.
        For fulltext query command.
        Args:
            keywords: List of keywords to query
        """
        contains = [ {"$contains": keyword} for keyword in keywords ]
        where_document = {"$and": contains}
        _logger.debug(f'collection.query_documents with where_document: {where_document}')
        self._ensure_connection(silent=True)
        results = self.collection.get(where_document=where_document)
        return results
    def query(self, query_text: str, top_k: int = None) -> list:
        """
        Perform a semantic search query.
        For vector query command.
        Args:
            query_text: The query text to search for
            top_k: Number of results to return (defaults to self.top_k)

        Returns:
            List of query results with documents, metadatas, and distances
        """
        if top_k is None:
            top_k = self.top_k

        # Query the collection
        self._ensure_connection(silent=True)
        results = self.collection.query(
            query_texts=[query_text],
            n_results=top_k
        )

        return results

    def hybrid_search(self, fulltext_keywords: List[str], vector_query_text: str, height_conditions: List[HeightCondition]) -> list:
        """
        Perform a hybrid search.
        Args:
            fulltext_keywords: List of keywords to search for
            vector_query_text: The query text to search for
            height_conditions: List of height conditions to search for
        """
        query = None
        knn = None
        where = None
        if height_conditions:
            height_conditions_query = [height_condition.to_query_string() for height_condition in height_conditions]
            if height_conditions_query:
                where = {"$and": height_conditions_query}
            else:
                where = height_conditions_query[0]
        if fulltext_keywords:
            query = {"where_document": {"$and": [{"$contains": keyword} for keyword in fulltext_keywords]}, "n_results":self.top_k*2}
            if where:
                query["where"] = where
        if vector_query_text:
            knn = {"query_texts": [vector_query_text], "n_results": self.top_k*2}
            if where:
                knn["where"] = where
        _logger.debug(f"query={query}, knn={knn}, where={where}")
        self._ensure_connection(silent=True)
        results = self.collection.hybrid_search(query=query, knn=knn, n_results=self.top_k)
        return results

    def format_results(self, results: Dict[str, List[Any]], query_text: str):
        """
        Format query results for display using rich

        Args:
            results: Results dictionary from collection.query()
            query_text: The original query text
        """
        if not results:
            self.console.print("\n[yellow]No results found[/yellow]\n")
            return

        _logger.debug(f"results={results}")

        # The results may be List[str] or List[List[str]]
        # But it can only has one item for the second format.
        ids = results.get('ids')
        multi_results = isinstance(ids[0], list)

        documents = results.get('documents', [])
        if documents and multi_results:
            documents = documents[0]
        metadatas = results.get('metadatas', [])
        if metadatas and multi_results:
            metadatas = metadatas[0]
        distances = results.get('distances', [])
        if distances and multi_results:
            distances = distances[0]
        # Ensure all lists have the same length
        max_len = max(len(documents), len(metadatas), len(distances))
        items = list(itertools.zip_longest(
            documents[:max_len] if documents else [None] * max_len,
            metadatas[:max_len] if metadatas else [{}] * max_len,
            distances[:max_len] if distances else [None] * max_len
        ))

        if not items:
            self.console.print("\n[yellow]No results found[/yellow]\n")
            return

        # Sort items by distance ascending
        def get_distance(item):
            if isinstance(item, dict):
                return item.get('distance', item.get('dist', float('inf')))
            elif isinstance(item, (list, tuple)):
                if len(item) >= 3:
                    return item[2] if item[2] is not None else float('inf')
                else:
                    return float('inf')
            else:
                return float('inf')
        items.sort(key=get_distance)

        # Use rich table for beautiful formatting
        table = Table(
            title=f"[bold cyan]Query:[/bold cyan] [white]'{query_text}'[/white]",
            show_header=True,
            header_style="bold magenta",
            box=box.ROUNDED,
            show_lines=True,
            padding=(0, 1)
        )
        table.add_column("Rank", style="cyan", width=4, vertical="middle", justify="center")
        table.add_column("Name", style="green", width=8, vertical="middle", overflow="fold")
        table.add_column("Place", style="green", width=14, vertical="middle", overflow="fold")
        table.add_column("Height", style="green", width=8, vertical="middle", justify="right", overflow="fold")
        table.add_column("Distance", style="yellow", width=12, vertical="middle", justify="right")
        table.add_column("Content Preview", style="dim white", width=50, overflow="fold")

        for i, item in enumerate(items, 1):
            if isinstance(item, dict):
                # Result is a dict with keys
                doc = item.get('document', item.get('doc', ''))
                metadata = item.get('metadata', item.get('metadata', {}))
                distance = item.get('distance', item.get('dist', None))
            else:
                # Result is a tuple (doc, metadata, distance)
                doc, metadata, distance = item if len(item) >= 3 else (item[0] if len(item) > 0 else None, item[1] if len(item) > 1 else {}, item[2] if len(item) > 2 else None)

            name = metadata.get('name', 'N/A') if metadata and isinstance(metadata, dict) else 'N/A'
            place = metadata.get('place', 'N/A') if metadata and isinstance(metadata, dict) else 'N/A'
            height = metadata.get('height', 'N/A') if metadata and isinstance(metadata, dict) else 'N/A'
            height = f"{height}" if height is not None and isinstance(height, (int, float)) else "N/A"
            dist_str = f"{distance:.4f}" if distance is not None else "N/A"
            content = doc[:80] + "..." if doc and len(doc) > 80 else (doc or "N/A")

            table.add_row(str(i), name, place, height, dist_str, content)

        self.console.print()  # Add spacing
        self.console.print(f"[bold green]Found {len(items)} result(s)[/bold green]")
        self.console.print(table)
        self.console.print()  # Add spacing after table

    def handle_hybrid_search_command(self, args: List[str]):
        try:
            if len(args) < 1:
                self.console.print("[red]Error: Usage: <query_text> [<keyword1> <keyword2> ...][/red]")
                return
            query_text = args[0]
            height_conditions = []
            fulltext_keywords = []
            for arg in args[1:]:
                if arg.startswith('height'):
                    height_condition = HeightCondition.parse_condition(arg)
                    if height_condition is None:
                        self.console.print(f"[yellow]Warning: Invalid height condition: {arg}. Will be treated as a fulltext keyword.[/yellow]")
                        fulltext_keywords.append(arg)
                    else:
                        height_conditions.append(height_condition)
                else:
                    fulltext_keywords.append(arg)
            results = self.hybrid_search(fulltext_keywords, query_text, height_conditions)
            return results

        except Exception as e:
            _print_exception(e, self.console)
    def show_help_commands(self):
        """
        Show the help commands using rich table format.
        """
        table = Table(
            title="[bold green]OceanBase SeekDB Hybrid Search Demo[/bold green]",
            show_header=True,
            header_style="bold magenta",
            box=box.ROUNDED,
            show_lines=True,
            padding=(0, 1)
        )
        table.add_column("Command", style="cyan", width=35, overflow="fold")
        table.add_column("Description", style="white", width=60, overflow="fold")

        # Add command rows
        table.add_row(
            "[bold]help, h[/bold]",
            "Show this help message"
        )
        table.add_row(
            "[bold]top <n>[/bold]",
            f"Set number of results to return (default: {self.top_k})"
        )
        table.add_row(
            "[bold]count[/bold]",
            "Show the number of items in the collection"
        )
        table.add_row(
            "[bold]list[/bold]",
            "List some items in the collection"
        )
        table.add_row(
            "[bold]get name=<tourism1,tourism2,...> place=<place1,place2,...>[/bold]",
            "Query data by metadata. Get the tourism information from the collection by names and places."
        )
        table.add_row(
            "[bold]fulltext <keyword1> <keyword2> ...[/bold]",
            "Fulltext with keywords query for the `documents`"
        )
        table.add_row(
            "[bold]vector <query_text>[/bold]",
            "Vector query (semantic search)"
        )
        table.add_row(
            "[bold]\[hs] <query_text> [<keyword1> <keyword2> ...] [height<comparison><value>][/bold]",
            "Hybrid search combining fulltext and vector search"
        )
        table.add_row(
            "[bold]exit, quit, q, bye[/bold]",
            "Exit the tool"
        )

        self.console.print()
        self.console.print(table)
        self.console.print()
    def run_interactive(self):
        """Run the interactive query shell."""
        # Set up command history
        self._setup_readline_history()

        self.show_help_commands()

        try:
            while True:
                try:
                    # Get user input
                    user_input = input("SeekDB> ").strip()

                    if not user_input:
                        continue

                    # Add to history (readline does this automatically, but we ensure it)
                    if READLINE_AVAILABLE and user_input:
                        try:
                            readline.add_history(user_input)
                        except Exception:
                            pass  # Ignore history errors

                    # Handle commands - check if first word is a known command
                    parts = user_input.split()
                    if parts:
                        command = parts[0].lower()

                        # List of all valid commands
                        # It's a command, handle it
                        if command in ['exit', 'quit', 'q', 'bye']:
                            self.console.print("[bold green]Goodbye![/bold green]")
                            self._save_history()
                            break
                        elif command == 'help' or command == 'h':
                            self.show_help_commands()
                            continue
                        elif command == 'count':
                            try:
                                count = self.collection.count()
                                self.console.print(f"\n[bold]Collection[/bold] [cyan]'{self.collection_name}'[/cyan] [bold]contains[/bold] [green]{count:,}[/green] [bold]items.[/bold]\n")
                            except Exception as e:
                                self.console.print(f"[red]Error getting collection count: {e}[/red]\n")
                            continue
                        elif command == 'list':
                            try:
                                results = self.list_items()
                                self.format_results(results, user_input)
                            except Exception as e:
                                self.console.print(f"[red]Error while listing collection: {e}[/red]\n")
                            continue

                        elif command == 'top':
                            try:
                                new_top_k = int(user_input.split()[1])
                                if new_top_k > 0:
                                    self.top_k = new_top_k
                                    self.console.print(f"[green]Top-K set to[/green] [cyan]{self.top_k}[/cyan]")
                                else:
                                    self.console.print("[red]Error: Top-K must be a positive integer[/red]")
                            except (IndexError, ValueError):
                                self.console.print("[red]Error: Usage: top <number>[/red]")
                            continue
                        elif command == 'get':
                            try:
                                args = user_input.split()
                                tourism_names = []
                                places = []
                                for arg in args[1:]:
                                    key, value = arg.split('=')
                                    if key.lower() == 'name':
                                        tourism_names.extend(value.split(','))
                                    elif key.lower() == 'place':
                                        places.extend(value.split(','))
                                results = self.get(tourism_names, places)
                                self.format_results(results, user_input)
                            except Exception as e:
                                _print_exception(e, self.console)
                                continue
                        elif command == 'fulltext':
                            try:
                                args = user_input.split()
                                keywords = args[1:]
                                results = self.query_documents(keywords)
                                self.format_results(results, user_input)
                            except Exception as e:
                                _print_exception(e, self.console)
                                continue
                        elif command == 'vector':
                            try:
                                args = user_input.split(maxsplit=1)
                                if len(args) < 2:
                                    self.console.print("[red]Error: Usage: vector <query_text>[/red]")
                                    continue
                                query_text = args[1]
                                results = self.query(query_text)
                                self.format_results(results, user_input)
                            except Exception as e:
                                _print_exception(e, self.console)
                                continue
                        elif command == 'hs':
                            args = user_input.split()
                            if len(args) < 2:
                                self.console.print("[red]Error: Usage: hs <query_text> [<keyword1> <keyword2> ...][/red]")
                                continue
                            results = self.handle_hybrid_search_command(args[1:])
                            if results:
                                self.format_results(results, user_input)
                        else:
                            results = self.handle_hybrid_search_command(user_input.split())
                            if results:
                                self.format_results(results, user_input)
                    else:
                        # Empty input (shouldn't reach here due to check above, but just in case)
                        continue

                except KeyboardInterrupt:
                    self.console.print("\n[yellow]Interrupted.[/yellow] Type [cyan]'exit'[/cyan], [cyan]'quit'[/cyan], or [cyan]'q'[/cyan] to quit or continue querying.")
                except Exception as e:
                    _print_exception(e, self.console)
                    _logger.exception("Error during query")
        finally:
            # Save history when exiting
            self._save_history()


def parse_args(argv):
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Interactive query tool for SeekDB vector database'
    )
    parser.add_argument(
        '--seekdb-mode', type=str, default='embeded',
        help='The mode of seekdb, can be one of {embeded, server}'
    )
    parser.add_argument(
        '--host', type=str, default='127.0.0.1',
        help='The host of the database (default: 127.0.0.1)'
    )
    parser.add_argument(
        '--port', type=int, default=2881,
        help='The port of the database (default: 2881)'
    )
    parser.add_argument(
        '--user', type=str, default='root',
        help='The user of the database (default: root)'
    )
    parser.add_argument(
        '--password', type=str, default='',
        help='The password of the database (default: empty)'
    )
    parser.add_argument(
        '--database', type=str, default='test',
        help='The database name (default: test)'
    )
    parser.add_argument(
        '--data-dir', type=str, default=os.environ.get('HOME', '') + '/seekdb',
        help='The directory of the data (default: $HOME/seekdb)'
    )
    parser.add_argument(
        '--embedding-model', type=str, default=MetaInfo.EMBEDDING_MODEL_NAME,
        help=f'The name of the embedding model (default: {MetaInfo.EMBEDDING_MODEL_NAME})'
    )
    parser.add_argument(
        '--collection-name', type=str, default=MetaInfo.COLLECTION_NAME,
        help=f'The name of the collection (default: {MetaInfo.COLLECTION_NAME})'
    )
    parser.add_argument(
        '--top-k', type=int, default=5,
        help='Number of results to return per query (default: 5)'
    )
    parser.add_argument(
        '--log-level', type=str, default='WARNING',
        help='The log level, can be one of {DEBUG, INFO, WARNING, ERROR, CRITICAL}'
    )
    return parser.parse_args(argv)


def main():
    """Main entry point."""

    argv = sys.argv[1:]
    args = parse_args(argv)

    logging.basicConfig(
        level=args.log_level.upper(),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    if args.seekdb_mode.lower() == 'embeded':
        client_settings = ClientSettings(path=args.data_dir, database=args.database)
    else:
        client_settings = ClientSettings(
            path=args.data_dir,
            host=args.host,
            port=args.port,
            user=args.user,
            password=args.password,
            database=args.database
        )

    try:
        tool = QueryTool(
            client_settings=client_settings,
            collection_name=args.collection_name,
            embedding_model_name=args.embedding_model,
            top_k=args.top_k
        )
        tool.run_interactive()
    except Exception as e:
        _print_exception(e)
        _logger.exception("Failed to start query tool")
        sys.exit(1)


if __name__ == '__main__':
    main()

