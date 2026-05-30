# TODO

## General issues

## SCPI

- Add SCPI management
  - Name, Institution
  - Share, wher value with history
  - Dividend by month
  - Dashboard to see evolution
  - Nu propriété

## Property

- load panels asynchronously, with a loading spinner, to avoid blocking the UI when loading a property with many entries
- Automatic estimation : add a button on the detail view to check current price of property with the French DVF API and add the value as a new entry if user confirms

## Finance

- Add CRUD views
  - saving, with a easy way to manage history and deposits
  - investing, in the same way, but with holdings in it
- In the finance, add the real time value of a holding using https://github.com/ranaroussi/yfinance
- All stats in the front page must be cached to not be computed each time. Add a mechanism for background operations. On the index page loading, check if the cached data is available and use it. If not, trigger a background task to compute the data and cache it for future requests. Indicate the date of the data in the front page, and when the user click on it it force a refresh of the data.
