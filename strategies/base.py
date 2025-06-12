# strategies/base.py

from abc import ABC, abstractmethod
import pandas as pds

class BaseStrategy(ABC):
    def __init__(self, symbol, timeframe, data):
        self.symbol = symbol
        self.timeframe = timeframe
        self.data = data  # Should be a pandas DataFrame

    @abstractmethod
    def generate_signal(self):
        """
        Should return one of: "LONG", "SHORT", or "HOLD"
        """
        pass

    @abstractmethod
    def name(self):
        pass
