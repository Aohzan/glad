# TODO

- In the property, add a detail view to show more information on the property:
  - graph to see the evolution of net/gross value for the past and the future
  - add a button on the detail view to check current price of property with the French DVF API and add the value as a new entry if user confirms
- In the finance, add the real time value of a holding using https://github.com/ranaroussi/yfinance
- All stats in the front page must be cached to not be computed each time. Add a mechanism for background operations. On the index page loading, check if the cached data is available and use it. If not, trigger a background task to compute the data and cache it for future requests. Indicate the date of the data in the front page, and when the user click on it it force a refresh of the data.
