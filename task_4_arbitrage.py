import math
import asyncio
import logging
import yfinance as yf
from typing import Dict, List, Set, Optional, Tuple

# Suppress yfinance warning logs to maintain a clean CLI interface
logging.getLogger('yfinance').disabled = True

class TriangularArbitrageScanner:
    """
    A quantitative trading engine that uses graph theory (Bellman-Ford) 
    to detect multi-hop arbitrage opportunities in financial markets.
    """
    def __init__(self):
        self.supported_assets: List[str] = ['USD', 'BTC', 'ETH', 'SOL']
        self.trading_pairs: List[str] = ['BTC-USD', 'ETH-USD', 'SOL-USD', 'ETH-BTC', 'SOL-BTC', 'SOL-ETH']
        
        # Nested dictionary representing our directed graph: graph[source][target] = {rate, weight}
        self.market_graph: Dict[str, Dict[str, dict]] = {asset: {} for asset in self.supported_assets}

    async def _fetch_live_price(self, trading_pair: str) -> Tuple[str, Optional[float]]:
        """Asynchronously fetches the latest closing price for a given pair."""
        try:
            # Pushing the blocking yfinance network call to a background thread
            historical_data = await asyncio.to_thread(yf.Ticker(trading_pair).history, period='1d')
            if historical_data.empty:
                return trading_pair, None
            
            latest_price = float(historical_data['Close'].iloc[-1])
            return trading_pair, latest_price
        
        except Exception:
            return trading_pair, None

    async def build_market_graph(self, enable_synthetic_inefficiency: bool = False) -> None:
        """
        Fetches live market data and constructs the directed graph.
        Weights are calculated as the negative natural logarithm of the exchange rate.
        """
        print("[*] Fetching live market data and constructing graph matrix...")
        
        fetch_tasks = [self._fetch_live_price(pair) for pair in self.trading_pairs]
        fetched_results = await asyncio.gather(*fetch_tasks)

        for trading_pair, price in fetched_results:
            if price is None:
                continue
            
            base_asset, quote_asset = trading_pair.split('-')

            # Inject synthetic pricing errors to guarantee the algorithm finds cycles during testing
            if enable_synthetic_inefficiency:
                if trading_pair == 'ETH-BTC':
                    price *= 1.05  # Synthetic 5% price gap
                if trading_pair == 'SOL-ETH':
                    price *= 0.92  # Synthetic 8% price gap

            # Forward Edge (Sell Base -> Buy Quote)
            self.market_graph[base_asset][quote_asset] = {
                'exchange_rate': price,
                'log_weight': -math.log(price)
            }

            # Reverse Edge (Sell Quote -> Buy Base)
            self.market_graph[quote_asset][base_asset] = {
                'exchange_rate': 1.0 / price,
                'log_weight': math.log(price)
            }
            
        print("[+] Market graph initialized and weights assigned.\n")

    def scan_for_arbitrage(self, starting_asset: str = 'USD') -> None:
        """
        Executes a modified Bellman-Ford algorithm to detect all negative-weight cycles,
        extracts the unique trade routes, and ranks them by profitability.
        """
        print("[*] Running exhaustive Bellman-Ford traversal...")
        
        # Initialize traversal state
        log_path_weights: Dict[str, float] = {asset: float('inf') for asset in self.supported_assets}
        path_predecessors: Dict[str, Optional[str]] = {asset: None for asset in self.supported_assets}
        log_path_weights[starting_asset] = 0.0

        total_nodes = len(self.supported_assets)

        # Step 1: Relax all edges |V| - 1 times
        for _ in range(total_nodes - 1):
            for current_asset in self.supported_assets:
                for target_asset, edge_data in self.market_graph[current_asset].items():
                    
                    new_weight = log_path_weights[current_asset] + edge_data['log_weight']
                    if new_weight < log_path_weights[target_asset]:
                        log_path_weights[target_asset] = new_weight
                        path_predecessors[target_asset] = current_asset

        # Step 2: On the |V|th iteration, identify any nodes that continue to relax (indicating a cycle)
        nodes_in_negative_cycles: Set[str] = set()
        
        for current_asset in self.supported_assets:
            for target_asset, edge_data in self.market_graph[current_asset].items():
                
                new_weight = log_path_weights[current_asset] + edge_data['log_weight']
                # Using a small epsilon (1e-9) to account for floating-point imprecision
                if new_weight < log_path_weights[target_asset] - 1e-9:
                    nodes_in_negative_cycles.add(target_asset)
                    path_predecessors[target_asset] = current_asset 

        if not nodes_in_negative_cycles:
            print("[-] Markets are perfectly efficient. No arbitrage opportunities found.")
            return

        # Step 3: Backtrack to extract isolated cycles and calculate profits
        unique_trade_routes = self._extract_unique_arbitrage_routes(nodes_in_negative_cycles, path_predecessors)
        
        arbitrage_leaderboard = []
        for route in unique_trade_routes:
            profit_percentage = self._calculate_route_profitability(route)
            arbitrage_leaderboard.append({
                "route_string": " ➔ ".join(route), 
                "expected_profit": profit_percentage
            })

        # Sort the leaderboard by highest profit first
        arbitrage_leaderboard.sort(key=lambda x: x['expected_profit'], reverse=True)
        self._display_dashboard(arbitrage_leaderboard)

    def _extract_unique_arbitrage_routes(self, suspect_nodes: Set[str], predecessors: Dict[str, str]) -> List[List[str]]:
        """Traces back from cycle-infected nodes and filters out duplicate loops."""
        unique_route_signatures: Set[str] = set()
        clean_routes: List[List[str]] = []

        for starting_node in suspect_nodes:
            current_node = starting_node
            
            # Step backward N times to guarantee we are inside the infinite loop
            for _ in range(len(self.supported_assets)):
                current_node = predecessors[current_node]
                
            cycle_path = []
            loop_anchor = current_node
            
            # Trace the loop until we hit our anchor again
            while True:
                cycle_path.append(current_node)
                current_node = predecessors[current_node]
                if current_node == loop_anchor and len(cycle_path) > 1:
                    break
            
            # Formatting the path for chronological execution
            cycle_path.append(loop_anchor)
            cycle_path.reverse()

            # Create a canonical signature to avoid listing the same loop from different starting nodes
            route_signature = "-".join(sorted(cycle_path[:-1]))
            if route_signature not in unique_route_signatures:
                unique_route_signatures.add(route_signature)
                clean_routes.append(cycle_path)

        return clean_routes

    def _calculate_route_profitability(self, trade_route: List[str]) -> float:
        """Simulates capital flowing through the route to determine absolute percentage yield."""
        simulated_capital = 1.0 
        
        for i in range(len(trade_route) - 1):
            base = trade_route[i]
            quote = trade_route[i+1]
            simulated_capital *= self.market_graph[base][quote]['exchange_rate']
        
        net_yield_percentage = (simulated_capital - 1.0) * 100
        return net_yield_percentage

    @staticmethod
    def _display_dashboard(leaderboard: List[dict]) -> None:
        """Renders the final CLI output table."""
        print("\n" + "="*70)
        print("🚀 ARBITRAGE OPPORTUNITY LEADERBOARD")
        print("="*70)
        print(f"{'Rank':<6} | {'Execution Route':<40} | {'Expected Yield'}")
        print("-" * 70)
        
        for index, entry in enumerate(leaderboard):
            rank_str = f"#{index+1}"
            print(f"{rank_str:<6} | {entry['route_string']:<40} | +{entry['expected_profit']:.3f}%")
            
        print("="*70 + "\n")


if __name__ == "__main__":
    # Toggle this to True to see the algorithm catch synthetic pricing gaps.
    # Toggle to False to scan real-world, highly efficient live data.
    ENABLE_SYNTHETIC_INEFFICIENCY = True 
    
    scanner = TriangularArbitrageScanner()
    
    # Run the async graph builder
    asyncio.run(scanner.build_market_graph(enable_synthetic_inefficiency=ENABLE_SYNTHETIC_INEFFICIENCY))
    
    # Run the synchronous Bellman-Ford traversal
    scanner.scan_for_arbitrage(starting_asset='USD')