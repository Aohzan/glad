# TODO

## General issues

## SCPI

Agis en tant qu'expert en architecture Django et ingénieur financier. Je souhaite ajouter la gestion des SCPI (Société Civile de Placement Immobilier) à mon application de gestion de patrimoine.

Voici mes fichiers de modèles actuels pour le contexte : `asset.py`, `lease.py`, `ledger.py` et `management.py`.

Je souhaite concevoir de nouveaux modèles Django en respectant les patterns déjà établis dans mon application (héritage de `BaseModel`, utilisation de `MoneyField` de `djmoney`, internationalisation avec `_()`, typage Python).

### Éléments requis pour les nouveaux modèles SCPI :

1. **Modèle `SCPI` (Le support) :**
   - Nom de la SCPI (ex: Corum Liffe, Pierval Santé).
   - Société de gestion.
   - Valeur de souscription actuelle (Prix de la part actuelle).
   - Valeur de retrait actuelle.

2. **Modèle `SCPIInvestment` (Les parts détenues par l'utilisateur) :**
   - Clé étrangère vers `SCPI`.
   - Date de souscription.
   - Nombre de parts (DecimalField à forte précision, ex: max_digits=10, decimal_places=4).
   - Prix d'achat unitaire (MoneyField).
   - Date de jouissance (date à partir de laquelle les dividendes sont versés).
   - **Gestion du Démembrement :**
     - Type de propriété via un TextChoices : Pleine Propriété (Full), Nue-propriété (Bare), Usufruit (Usufruct).
     - Si Nue-propriété : Date de début, Date de fin du démembrement, et Clé de répartition (la valeur en % de la nue-propriété à l'achat, ex: 65.00%).

3. **Intégration comptable (Dividendes et Plus-values) :**
   - Je souhaite réutiliser mon modèle existant `PropertyLedgerEntry` (dans `ledger.py`) pour suivre les flux financiers des SCPI (les dividendes perçus).
   - Propose-moi les modifications à faire sur `ManagementCategory` dans `ledger.py` pour ajouter les catégories nécessaires (ex: `SCPI_DIVIDEND`), et ajoute une relation optionnelle (`null=True, blank=True`) sur `PropertyLedgerEntry` vers le nouveau modèle `SCPIInvestment`.

### Méthodes et Propriétés intelligentes à implémenter :

Dans le modèle `SCPIInvestment`, code les méthodes suivantes :
- `get_purchase_value()` : Nombre de parts * Prix d'achat.
- `get_current_full_value(as_of_date)` : Calcule la valeur totale brute actuelle (Nombre de parts * Valeur de souscription de la SCPI).
- `get_estimated_value(as_of_date)` : Prend en compte le démembrement. Si l'utilisateur est nu-propriétaire, calcule la valeur de sa nue-propriété qui augmente linéairement (ou via une formule financière standard) au fil du temps jusqu'à atteindre 100% de la valeur de la part à la date de fin du démembrement. Si la date de fin est dépassée, l'actif passe automatiquement à 100% (reconstitution de la pleine propriété).
- `get_capital_gain()` : Plus-value latente basée sur la valeur actuelle (retrait ou souscription) par rapport au prix d'achat.

Génère le code Python propre, documenté avec des docstrings, et explique brièvement tes choix pour le calcul de la revalorisation de la nue-propriété.

## Property

- Automatic estimation : add a button on the detail view to check current price of property with the French DVF API and add the value as a new entry if user confirms

## Finance

- In the finance, add the real time value of a holding using https://github.com/ranaroussi/yfinance
- All stats in the front page must be cached to not be computed each time. Add a mechanism for background operations. On the index page loading, check if the cached data is available and use it. If not, trigger a background task to compute the data and cache it for future requests. Indicate the date of the data in the front page, and when the user click on it it force a refresh of the data.
