# TODO

## General issues

- generate_fixtures.py : review the financial fixtures, to generate 70% profit and 30% loss on accounts/holdings, ensure coherence between deposits and global, to get a 8% global profit on the front page, and to have a more realistic distribution of profits/losses across accounts/holdings. Also, add more accounts/holdings to have a more complete dataset. Get something like 100k€ on PEA, 40k€ on a life insurance, 70K on some saving accounts. Create SCPI: the first with 20k invested 3 years ago, divident every quarter, between 4-6%. the second 10k since 18 months, dividend every month since 14 months, between 3-5%. The third 15k since 2 years in nu-porperty.

## Property

- Automatic estimation : add a button on the detail view to check current price of property with the French DVF API and add the value as a new entry if user confirms

## Finance

- In the finance, add the real time value of a holding using https://github.com/ranaroussi/yfinance
- All stats in the front page must be cached to not be computed each time. Add a mechanism for background operations. On the index page loading, check if the cached data is available and use it. If not, trigger a background task to compute the data and cache it for future requests. Indicate the date of the data in the front page, and when the user click on it it force a refresh of the data.
