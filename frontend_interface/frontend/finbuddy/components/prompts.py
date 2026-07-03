etf_example1 = """show to me some etf on emerging markets
"""
etf_example2 = """show to me some etf on emerging markets
"""


eq_portfolio_example1 = """backtest portfolio:
    i want to filter tickers in sp500.
    filter mining and war related sectors.
    selection long only:
    exclude bottom 10% of tickers with lower esg score
    i want to rebalance every start of the month
 """


eq_portfolio_example2 = """
backtest portfolio:
    universe:
    i want to filter tickers in sp500. 
    include only tech related sectors
    long only :
    exclude bottom 10% esg percentile for each date   
    i want to rebalance every start of the month
    start from 2019
"""
eq_portfolio_example3 = """backtest backtest portfolio:
i want ot filter on index sp500, ADV>2e06, close price >1.
from 2017
 long part: 
   select top 25% of tickers ranked by (momentum of close price in last 3 months, by ticker)
 short part: 
   select bottom 25% of tickers ranked by (momentum of close price in last 3 months, by ticker)

 I want to rebalance the portfolio once a month

"""

eq_portfolio_example3 = """tilt a portfolio to quality
"""




eq_portfolio_example4 = """create a portfolio to tracking SP500,
with maximum 100 stocks
excluding 'High ESG Risk' esg_rating, and oil an mining companies as well
"""


fi_portfolio_example1 = """ backtest a USA bonds ladder maximum duration 10 years starting from 2015-06-12
"""

fi_portfolio_example2 = """ backtest a USA bonds rolling maximum duration 15 years ,  starting from 2017-01-12
"""

asset_allocation_example1 = """ i want to create an equity portfolio filtering on sp500 sector constraints: Energy:20%, Financials:20%, Consumer_Goods:5% start in 2021 
and a bond portfolio ladder maximum 1 years minimum 5 years start in 2021, 
then allocate weights 50/50 to the 2 portfolios
"""

asset_allocation_example2 = """ backtest a 60% equity, 40% Fixed income portfolio. 
For equity:
Long only , filte on sp500, and exclude 20% of tickers with bottom ESG score
For fixed income keep gov bonds maximum 10 years duration. 
then allocate weights 60/40 to the 2 portfolios
"""

thematic_example = """It is now May 2024, given current macroeconomic situation,
            inflation going a bit down, 
            rates level as well from a hig level of 5.5% with forecast of 3 custs (0.25%) by end of the year,
            and in scenario of Trump and Republican Party winning election.
            Consider Trump political choices and business and industries that can outperform
            generate a thematic portfolio that take advantage and outperform
"""
