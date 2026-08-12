import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from intelligence.benchmark_intelligence import BenchmarkPipeline
from core.logging import logger

def main():
    logger.info("Starting Benchmark Pipeline Test...")
    pipeline = BenchmarkPipeline()
    dna = pipeline.run(force_reanalyze=False)
    logger.info(f"Test complete. Total sources: {dna.source_count}")

if __name__ == "__main__":
    main()
