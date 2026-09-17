# LMNP au régime réel : comment Glad calcule la liasse

Ce document décrit, étape par étape, le calcul réalisé par
`property/services/tax_lmnp.py` pour l'aide à la déclaration des revenus de
location meublée non professionnelle (LMNP) au régime réel simplifié.
Chaque étape cite la case du formulaire officiel, la formule, la cellule
équivalente du classeur de référence (simulateur LMNP.blog, onglet
`Calcul_Liasse`) et la source juridique. Les constantes datées (seuils, taux,
durées) sont dans `property/services/lmnp_rules.py`.

> Glad est une aide : il ne remplace ni la liasse officielle ni l'avis d'un
> expert-comptable.

## Vue d'ensemble

Le calcul est une **passe chronologique** : pour chaque exercice depuis le début
de l'activité, `compute_year()` transforme les entrées de l'année
(`LmnpYearInputs`) en résultat (`LmnpYearResult`) et transmet à l'année
suivante ce qui se reporte (`FiscalCarry` : amortissements différés et
déficits non imputés). Une seule activité LMNP existe par contribuable : la
couche fiscale (plafond 39 C, reports, déficits) est calculée pour l'ensemble
des biens, le détail par bien ne sert qu'aux lignes du compte de résultat et
au 2033-C.

```
ledger + immobilisations ──► LmnpYearInputs(N) ──► compute_year ──► LmnpYearResult(N)
                                                        ▲   │
                                          FiscalCarry(N-1) FiscalCarry(N)
```

## 1. Immobilisations et amortissements (2033-C)

| Étape | Règle | Classeur | Source |
|---|---|---|---|
| Valeur immobilisée | prix d'achat, majoré des frais d'acquisition (notaire, agence, frais de crédit) **uniquement** si le bien a été acheté l'année du début d'activité et si l'option « frais en amortissement » est retenue (option irrévocable) | `1-Biens_Immos!Z277:Z278` | BOI-BIC-CHG-20-20-10 |
| Début d'amortissement | `max(date d'achat, date de début d'activité LMNP)` (`Property.amortization_start_date`) | `1-Biens_Immos!Z280` | — |
| Ventilation par composants | terrain = `land_percentage` (non amorti) ; le reste est réparti au prorata des quotes-parts par défaut : gros œuvre 45 % / 70 ans, électricité 6 % / 30 ans, étanchéité 7 % / 25 ans, toiture 8 % / 25 ans, agencements 19 % / 12 ans | `1-Biens_Immos!F32:G38` | BOI 4 A-13-05 (composants) |
| Dotation annuelle | linéaire : `valeur / durée` | `1-Biens_Immos!Z8…` | art. 39-1-2° CGI |
| Première année | prorata temporis en base **30/360** : `valeur / (durée × 360) × DAYS360(début, 31/12)` (`days360()` dans `property/utils/date_utils.py`) | `DAYS360(...)` | BOI-BIC-AMT-20-10-30 |
| Dernière année | reliquat `valeur − Σ dotations précédentes`, pour que le cumul soit exactement égal à la valeur | `W − SUM(...)` | — |
| Mobilier, travaux | immobilisés au-dessus de 600 € HT (tolérance), sinon passés en charges | — | BOI-BIC-CHG-20-30-10 § 90 |

Cases : 2033-C 420/430/450/470 (valeurs début), 426/436/456/476 (fin),
572 (dotations de l'exercice = 2033-B 254), 576 (cumul fin d'exercice).

## 2. Compte de résultat (2033-B, partie A)

| Case | Contenu | Champ | Classeur |
|---|---|---|---|
| 218 | loyers, charges refacturées, reversements du gestionnaire | `revenue_218` | `E33` |
| 209 | autres produits | `other_income_209` | — |
| 242 | autres charges externes : gestion, copropriété, entretien, assurances (PNO, GLI, emprunteur), frais de comptabilité, petites dépenses | `external_charges_242` | `E34` |
| 244 | impôts et taxes : taxe foncière, CFE | `taxes_244` | `E35` |
| 243 | dont CFE | `cfe_243` | `E36` |
| 254 | dotations aux amortissements (= 2033-C 572) | `depreciation_254` | `E37` |
| **270** | résultat d'exploitation = 218 + 209 − 242 − 244 − 254 | `operating_result_270` | `E38` |
| 294 | charges financières (intérêts d'emprunt) | `financial_charges_294` | `E39` |
| **310** | bénéfice ou perte = 270 − 294 | `accounting_result_310` | `E40` |

Les catégories d'écritures (`ManagementCategory`) portent directement leur
ligne cerfa ; le dépôt de garantie, le capital remboursé et le fonds travaux
ALUR n'entrent pas dans le résultat.

## 3. Plafonnement de l'amortissement (article 39 C)

L'amortissement d'un bien loué par une personne physique ne peut ni créer ni
augmenter un déficit (art. 39 C II CGI ; BOI-BIC-AMT-20-40-10-20 § 40 à 70).

| Étape | Formule | Champ | Classeur |
|---|---|---|---|
| Plafond | `max(0, produits − (242 − frais de comptabilité) − 244 − 294)` | `depreciation_cap_39c` | `E44` |
| Amortissement déduit | `min(254, plafond)` | `depreciation_deducted` | `MIN(E37, E44)` |
| **318** réintégration | `254 − déduit` (jamais plus que la dotation) | `depreciation_reintegrated_318` | `E52` |
| **350** déduction | `min(stock différé début, max(0, 310 + 318))` : les amortissements différés des années précédentes sont déduits dès qu'un exercice est bénéficiaire, sans créer de déficit | `deferred_depreciation_used_350` | `E59` |
| Stock différé fin | `début + 318 − 350`, reportable **sans limite de durée** (SUIV39C) | `deferred_depreciation_end` | `E61` |

Les frais de comptabilité restent déductibles mais ne sont pas des « charges
afférentes au bien » : ils n'abaissent pas le plafond (§ 70). Un déficit dû
aux charges elles-mêmes n'est **pas** réintégré : il devient un déficit
reportable (étape 4).

## 4. Résultat fiscal et déficits (2033-B, partie B)

| Case | Formule | Champ | Classeur |
|---|---|---|---|
| **352** | résultat fiscal avant imputation des déficits = 310 + 318 − 350 (signé) | `fiscal_result_352` | `E63` |
| déficits disponibles | déficits des années N−1 à N−10 non encore imputés | `prior_deficits_start` | `E65` |
| **360** | déficits antérieurs imputés = `min(Σ disponibles, max(0, 352))`, les plus anciens d'abord | `prior_deficits_used_360` | `E66` |
| **370** | résultat fiscal après imputation = 352 − 360 si 352 > 0, sinon 352 | `fiscal_result_370` | `E69` |
| déficits fin | déficits restants + le déficit de l'année si 352 < 0 ; un déficit de l'année N est imputable de N+1 à N+10 puis perdu | `deficits_end` | `E98:E108` |

Source : art. 156 I 1° ter CGI (déficits BIC non professionnels imputables
uniquement sur des bénéfices de même nature des dix années suivantes).

## 5. 2031 et 2042-C PRO

| Case | Contenu | Champ |
|---|---|---|
| 2031 C (7) | résultat fiscal avant imputation des déficits = 352 | `fiscal_result_352` |
| 2031 C (1/4) | bénéfice imposable ou déficit déductible = 370 | `fiscal_result_370` |
| 2031-bis I | BIC non professionnels : 352 en bénéfice ou déficit | — |
| 2042-C PRO **5NA** | revenus imposables, régime réel, cas général = `max(0, 370)` | `case_5na` |
| 2042-C PRO **5NY** | déficit de l'année = `max(0, −352)` | `case_5ny` |
| 2042-C PRO **5CD** | durée de l'exercice en mois : `12 − mois de début + 1` la première année, 12 ensuite | `case_5cd` |
| 2042-C PRO **5GJ … 5GA** | déficits des années N−1 … N−10 non encore déduits | `deficit_cases` |

Depuis les revenus 2023, il n'existe plus de majoration de 1,25 pour
non-adhésion à un organisme de gestion agréé (anciennes cases 5NK / 5NZ).
Depuis les revenus 2025, la réduction d'impôt pour frais de comptabilité et
d'adhésion à un OGA (2/3 des frais, 915 € maximum) est supprimée par la loi de
finances 2025 (art. 11) ; les frais sont simplement déductibles en ligne 242.

## 6. Règles datées (revenus 2025 et 2026)

| Règle | Revenus 2025 (déclarés en 2026) | Revenus 2026 (déclarés en 2027) | Source |
|---|---|---|---|
| Micro-BIC longue durée et meublé de tourisme classé : plafond / abattement | 77 700 € / 50 % | 83 600 € / 50 % | art. 50-0 CGI, revalorisation triennale 2026 |
| Micro-BIC meublé de tourisme non classé | 15 000 € / 30 % | 15 000 € / 30 % | loi « Le Meur » du 19 novembre 2024 |
| Abattement minimum micro-BIC | 305 € | 305 € | art. 50-0 CGI |
| Prélèvements sociaux | 18,6 % | 18,6 % | LFSS 2026 |
| Report du déficit BIC non professionnel | 10 ans | 10 ans | art. 156 I 1° ter CGI |
| Report des amortissements différés (39 C) | illimité | illimité | BOI-BIC-AMT-20-40-10-30 |
| Réintégration des amortissements dans la plus-value de cession | cessions à partir du 15 février 2025 | idem | LF 2025 art. 84, art. 150 VB II 8° CGI |
| Plafonnement de l'amortissement à 2 % par an | rejeté | rejeté | débats PLF 2026 |

Glad ne calcule que le régime réel ; les seuils micro-BIC sont conservés dans
`lmnp_rules.py` à titre documentaire.

## 7. Figer et exporter une année

Depuis la page « LMNP réel — Comptabilité », le bouton **Figer l'exercice**
enregistre une copie JSON de tous les chiffres calculés
(`LmnpDeclarationSnapshot`, service `property/services/lmnp_snapshot.py`).
Les liasses figées restent consultables avec les mêmes onglets que le tableau
de bord et se téléchargent en PDF (`property/services/lmnp_pdf.py`, fpdf2,
polices DejaVu embarquées). Le bouton **Télécharger le PDF** produit le même
document à partir des chiffres en direct, sans rien enregistrer.

## 8. Vérifier le calcul

`property/tests/test_lmnp_golden_excel.py` rejoue le scénario à deux biens du
classeur de référence (Orléans et Angers, exercice 2025) et compare chaque
ligne au classeur : dotation 4 460,82 €, résultat comptable −3 796,02 €,
plafond 39 C 664,80 €, réintégration 318 de 3 796,02 €, résultat fiscal 0,
dotation 2026 de 7 015,04 €.

```
ENV_FILE=.env.dev uv run pytest property/tests/test_lmnp_golden_excel.py property/tests/test_lmnp_conformity.py -q
```

## Sources

- [Article 39 C du CGI](https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000029355753)
- [BOI-BIC-AMT-20-40-10-20 : amortissement fiscalement déductible des biens loués](https://bofip.impots.gouv.fr/bofip/4527-PGP.html/identifiant=BOI-BIC-AMT-20-40-10-20-20170301)
- [Article 156 du CGI (déficits)](https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000049641650)
- [Article 50-0 du CGI (micro-BIC)](https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000050833584)
- [Suppression de la réduction d'impôt OGA (LF 2025)](https://www.legifiscal.fr/actualites-fiscales/4158-loi-finances-2025-suppression-reduction-impot-accorde-autoentrepreneurs-adherents-oga.html)
- [Seuils micro-BIC 2026](https://www.legifiscal.fr/actualites-fiscales/4436-nouveaux-seuils-micro-entreprises-annee-2026.html)
- Formulaires officiels enregistrés dans `declaration/` (2031, 2031-bis, 2033-A/B/C/D, annexe libre).
