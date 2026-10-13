# Budget du foyer : comment Glad calcule le budget annuel

Ce document décrit le budget annuel du foyer (`budget/`) : ce qui est saisi,
ce qui est lu dans le reste de l'application, et le calcul des indicateurs.
Les calculs sont dans `budget/services/summary.py`.

## Vue d'ensemble

Un budget couvre une **année civile**. Il contient :

- les **lignes saisies** : un libellé, une catégorie, un montant **annuel** et
  une personne (vide pour tout le foyer). Il n'y a pas de récurrence : le
  montant est celui de l'année entière, les pages affichent l'équivalent
  mensuel (÷ 12). Dans le formulaire, le bouton « Montant mensuel × 12 »
  convertit un montant mensuel tapé ;
- les **lignes automatiques**, recalculées à chaque affichage et jamais
  copiées dans le budget (voir plus bas).

Les catégories forment un **arbre commun à toutes les années**, de trois
niveaux au plus (par exemple `Transport > Carburant`). Chaque catégorie a un
type : revenu, dépense ou épargne. Une sous-catégorie prend le type de son
parent. Les catégories par défaut sont créées à la demande, dans la langue de
l'utilisateur, et restent modifiables.

```
lignes saisies ─┐
ledger + crédits ┼──► arbres ressources / dépenses / épargne ──► indicateurs, sankey
SCPI, comptes  ─┘
```

## Lignes automatiques

| Source | Côté | Calcul |
|---|---|---|
| Ledger des biens | revenus et dépenses, par bien puis par catégorie de gestion | occurrences de l'année, récurrences comprises (projetées pour une année future) ; les dépôts de garantie (`deposit_in`, `deposit_out`) sont exclus |
| Échéanciers des crédits | dépenses, par bien : capital, intérêts, assurance | `Schedule.paid_between(1er janvier, 31 décembre)` ; les écritures de crédit du ledger sont ignorées dès qu'un bien a un crédit, comme dans le cash-flow des biens |
| Dividendes SCPI | revenus | dividendes nets payés dans l'année |
| Souscriptions SCPI | épargne | `nombre de parts × prix unitaire` des souscriptions de l'année |
| Versements sur les comptes | épargne (net positif) ou désépargne (net négatif, côté ressources) | versements et retraits de l'année par compte d'épargne ou d'investissement, plus la valeur d'ouverture d'un compte ouvert dans l'année, selon leur origine (voir plus bas) |

Un bien compte s'il est détenu pendant l'année (acheté avant le 31 décembre,
vendu après le 1er janvier ou pas vendu). Les biens peuvent être exclus un
par un dans les réglages du budget, et chaque source peut être désactivée.
Seuls les montants dans la devise de référence sont comptés.

## Origine des versements

Chaque versement ou retrait d'un compte a une **origine**, obligatoire,
« Inconnue » par défaut :

| Origine | Traitement dans le budget |
|---|---|
| Revenus ou dépenses du foyer | un versement est de l'épargne prise sur les revenus, un retrait une ressource (désépargne) |
| Virement entre comptes | ignoré : l'argent ne fait que changer de compte |
| Exceptionnelle (vente, héritage, donation…) | un versement apparaît en « Apports exceptionnels » côté ressources et en épargne côté emplois, sans compter dans les revenus ni dans le taux d'épargne ; un retrait exceptionnel (achat d'un bien…) est ignoré |
| Inconnue | origine **devinée** : c'est un virement entre comptes si un autre compte a un mouvement de signe opposé et de même montant, d'origine inconnue ou « virement », à 7 jours au plus (le plus proche est apparié, y compris de part et d'autre du 1er janvier) ; sinon, revenus ou dépenses du foyer |

La valeur d'ouverture d'un compte ouvert dans l'année compte comme un
versement, avec l'origine choisie sur le compte (« Origine de la valeur
d'ouverture », inconnue par défaut) : ouvrir un PEA avec l'argent d'un livret
est reconnu comme un virement. La page du budget signale le nombre de mouvements
dont l'origine a été devinée, avec leur détail et un lien vers chaque compte
pour la préciser.

## Vue du foyer ou d'une personne

La vue **foyer** compte toutes les données. La vue d'une **personne** compte :

- en totalité les lignes et actifs nommés pour elle ;
- les lignes du foyer (sans personne) et les actifs sans propriétaire,
  **divisés par le nombre d'adultes** ;
- rien des éléments nommés pour un autre membre.

Un enfant ne reçoit donc que ce qui est nommé pour lui. Pour un actif détenu
à plusieurs, la part vient des lignes de propriété (`Ownership`). Pour un bien
démembré, les flux sont répartis par côté
(`base.services.ownership.flow_ratio`) : l'usufruitier perçoit les loyers et
paie les charges courantes, le nu-propriétaire paie les échéances de crédit et
les souscriptions. Les dividendes SCPI vont aux parts en pleine propriété ou
en usufruit, au prorata du nombre de parts.

## Indicateurs

| Indicateur | Formule |
|---|---|
| Revenus | lignes de revenus + revenus du ledger + dividendes SCPI (hors désépargne et apports exceptionnels) |
| Dépenses | lignes de dépenses + dépenses du ledger + échéances de crédit (capital, intérêts, assurance) |
| Épargne | lignes d'épargne + versements nets sur les comptes (apports exceptionnels compris) + souscriptions SCPI |
| Solde | `revenus + désépargne + apports exceptionnels − dépenses − épargne` : « non affecté » s'il est positif, « déficit » s'il est négatif |
| Taux d'épargne | `(revenus − dépenses) / revenus` |
| Taux d'épargne avec le capital | `(revenus − dépenses + capital remboursé) / revenus` : le capital remboursé constitue aussi un patrimoine |
| Taux d'endettement | `mensualités / (revenus saisis + 70 % des loyers et dividendes SCPI)`, avec mensualités = échéances des crédits immobiliers, assurance comprise, + lignes des catégories marquées « remboursements de crédit » ; signalé au-delà de 35 % (recommandation du HCSF) |
| Reste à vivre | `(revenus − mensualités) / 12` |

Le fonds d'urgence (page Répartition) est dimensionné sur les dépenses du
budget de l'année en cours, ou du dernier budget antérieur, divisées par 12.
Sans budget, il reprend les dépenses mensuelles saisies sur la page.

## Comparaison avec l'année précédente

Chaque nœud a une clé stable d'une année à l'autre : la catégorie, la ligne
(catégorie, libellé et personne), le bien ou le compte. Les totaux de l'année
précédente sont rapprochés par clé. L'inflation de l'année (indice des prix à
la consommation de l'INSEE, de décembre à décembre ou jusqu'au dernier mois
publié) permet de lire les écarts en euros constants.

**Copier une année** crée le budget d'une autre année avec les réglages et
toutes les lignes, chaque montant étant revalorisé d'un pourcentage (par
défaut l'inflation des 12 derniers mois publiés), arrondi au centime.

## Sankey

Le diagramme (`static/js/sankey.js`, sans dépendance) relie les ressources, à
gauche, aux dépenses et à l'épargne, à droite, par un nœud central. Chaque
compte y compte pour son flux net de l'année (apports exceptionnels compris),
et les retraits des comptes sont déduits de leurs versements, au prorata de
chaque compte : un livret vidé sur le compte courant puis replacé sur un PEA
n'apparaît pas des deux côtés. Les tableaux gardent le détail par compte. Chaque
côté étant un arbre, chaque profondeur est une colonne, les nœuds sont
empilés dans l'ordre de l'arbre et centrés sur leur parent. Un clic plie ou
déplie un groupe. Les couleurs viennent des jetons CSS `--g-*` et suivent le
thème.

## Import CSV et prompt IA

Le fichier contient une ligne par ligne de budget, avec un en-tête :

```
kind;category;label;amount;person;notes
expense;Transport > Carburant;Carburant;1 450,00;;
income;Salaires;Salaire;42000;Alice;
```

- `kind` : `income`, `expense` ou `saving` (ou `revenu`, `dépense`,
  `épargne`), facultatif si la catégorie existe ;
- `category` : chemin de la catégorie, niveaux séparés par `>` (comparé sans
  tenir compte de la casse ni des accents) ;
- `amount` : montant annuel ; le signe est ignoré, `1 200,50`, `1.200,50` et
  `1,200.50` sont acceptés ;
- `person` : prénom ou identifiant d'un membre, vide (ou `foyer`) pour le
  foyer.

Le séparateur (`;` ou `,`) et l'encodage (UTF-8 ou Latin-1) sont détectés.
Un aperçu liste les lignes valides, les erreurs et les catégories à créer
(option « créer les catégories manquantes ») avant l'import. L'export produit
le même format.

La page **Prompt pour une IA** fournit un texte à donner à l'assistant de son
choix avec l'export des opérations bancaires : il demande de regrouper les
opérations en lignes annuelles au format ci-dessus, en utilisant les
catégories existantes et les prénoms du foyer, et d'écarter les flux déjà
suivis par Glad (crédits et loyers des biens, versements sur les comptes) pour
éviter de les compter deux fois. Les opérations bancaires partent alors chez
ce service.
