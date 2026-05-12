# TODO

## General issues

## LMNP accounting

Référence Excel: /home/matthieu/Nextcloud/Documents/Immobilier/Suivi LMNP_unlocked.xlsx

### FIXÉ ✓
- **#2** 2033-A ACTIF 2 Charges constatées d'avance : champ `charges_constatees_avance` ajouté dans `get_bilan_data` (valeur 0, non suivi)
- **#3** 2033-A Capital individuel : corrigé — utilisait `taxable_result` (fiscal) au lieu de `cerfa_310` (comptable)
- **#4** 2033-A Résultat de l'exercice : corrigé — le bilan 2033-A doit afficher le résultat COMPTABLE (cerfa_310), pas le résultat fiscal

### À INVESTIGUER
- **#1 & #7** Déficit 432€ vs 0 dans l'Excel : le `result_before_amort` de l'app est -432€ au lieu de 664.80€.
  Écart = 1096.80€ en charges. Comparer le détail "Autres charges ext." + "Charges financières" dans l'app
  (section dépliable dans 2033-B) avec l'Excel. Probable double comptage ou entrée en trop.
  Excel attendu : loyers 7588.17, charges 1612.43 (inclut assurance emprunteur ~201€), taxes 708.03, intérêts 4602.91
- **#6** Amortissements excédentaires (art. 39-4) : découlera de la correction du #1 (si result > 0, l'amort déductible sera correctement plafonné)

### FEATURE REQUEST (DONE)
- **#5** ✓ Tableau d'amortissement CSV : `PropertyLoanSchedule` remplacé par `PropertyLoanAmortizationEntry`. Import CSV (bouton dans l'onglet prêts), génération auto, effacement. Si aucune entrée → calcul auto de repli.

## Property / Automatic estimation

add a button on the detail view to check current price of property with the French DVF API and add the value as a new entry if user confirms

## Finance

- In the finance, add the real time value of a holding using https://github.com/ranaroussi/yfinance
- All stats in the front page must be cached to not be computed each time. Add a mechanism for background operations. On the index page loading, check if the cached data is available and use it. If not, trigger a background task to compute the data and cache it for future requests. Indicate the date of the data in the front page, and when the user click on it it force a refresh of the data.
