# Rental management

Glad follows the leases you manage yourself, from the application of a candidate to the return of the deposit. A lease is managed by an agency as long as a management mandate of the property covers today: the agency handles it, and the rental pages only show it.

The documents for the tenant (lease, inventory, receipts, statements, emails) are written in French: they follow the French law (loi n° 89-462 du 6 juillet 1989).

## Setting up

1. Enter your postal address in **Settings** (or, for a SCI, the landlord name and address on the property): it is written on the receipts and the lease.
2. On the property, enter its construction year (it decides the diagnostics to annex) and whether it is in a tight rental zone (*zone tendue*).
3. To send emails, configure the SMTP server (`EMAIL_*` variables). Without it, the emails are only written to the logs.
4. To sign online, run a [Documenso](https://documenso.com) instance and set `DOCUMENSO_URL` and `DOCUMENSO_API_TOKEN`. Without it, sign on paper and add the scan to the documents of the lease.

## Workflow

| Step | Where |
| --- | --- |
| Record the candidates, their documents and decide | **Rental management › Applications** |
| Accept one: the lease form opens with the candidate as the tenant | Application page |
| Read the lease PDF, then send it for signature | Lease › Summary |
| Do the entry inventory room by room on the phone, then have it signed | Lease › Inventories |
| Record the deposit received, upload the insurance certificate | Lease › Summary (move-in), Documents |
| Create the rent schedule, check the payments as they arrive | Lease › Payments, **Entries to check** |
| Send the receipts, rent notices and reminders (or let them go automatically) | Lease › Payments, Emails |
| Mark the recoverable expenses, reconcile the charges every year | Property ledger, Lease › Charges |
| Record the notice, do the exit inventory, return the deposit, close the lease | Lease › Departure |

A payment is the occurrence of the recurring rent (or charges) entry checked as received, for the amount actually received. A one-off rent entry linked to the lease (a prorated first rent, a catch-up payment) counts in the month it refers to.

## Automatic emails

On the lease form, *Send the rent calls* emails the rent notice a week before each due date, and *Send the receipts* emails the receipt the morning after a month is fully checked (for the last two months only, so that enabling it does not send the whole history). The `rental_daily` job runs at 07:30; every email is listed in the Emails tab of the lease.

## Legal rules

The dated rules live in `rental/rules.py`, with their source:

- deposit cap: 1 month of rent empty, 2 months furnished, none for a mobility lease;
- legal duration: 3 years empty, 1 year furnished, 9 months for a student, 1 to 10 months for a mobility lease;
- notice of the tenant: 3 months empty (1 month in a tight zone), 1 month furnished; notice of the landlord: 6 months empty, 3 months furnished, before the end of the term;
- deposit return: 1 month after the keys when the exit inventory matches the entry one, 2 months otherwise; 10 % of the rent per started month of delay; up to 20 % kept until the co-ownership accounts;
- diagnostics: DPE and risks always, lead before 1949, asbestos before July 1997, electricity and gas after 15 years;
- documents of an application: allowed and forbidden ones (décret n° 2015-1437);
- furniture of a furnished dwelling (décret n° 2015-981).

Glad helps you follow these rules; it does not replace legal advice. Read the lease PDF before having it signed: what Glad does not know is left as a dotted line.
