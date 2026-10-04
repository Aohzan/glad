# CHANGELOG

<!-- version list -->

## v1.5.0 (2026-10-04)

### Bug Fixes

- **dashboard**: Name the unnamed loans in the deadlines
  ([`c88f6ce`](https://github.com/Aohzan/glad/commit/c88f6cecc358d02917c41f555efd0501568a1530))

- **dashboard**: Rebuild the net worth history after the loan fixes
  ([`338b26d`](https://github.com/Aohzan/glad/commit/338b26df7b878ec91295923816b2cdfa38b8d603))

- **dashboard**: Refresh net worth snapshots after bulk writes
  ([`437c3fc`](https://github.com/Aohzan/glad/commit/437c3fce3d2c9296bae3c07e9b1105cc15c09aec))

- **finance**: Require the sale date of an inactive other asset
  ([`423e3d5`](https://github.com/Aohzan/glad/commit/423e3d503d376fe8c1117e6ead6e67a02043ae02))

- **lmnp**: Fall back to the loan schedule for the interest and insurance of unfrozen years
  ([`bd40bba`](https://github.com/Aohzan/glad/commit/bd40bba358309db387aa1fba6cf96977894f6e2b))

- **property**: Align the stacked loan bars on a common month axis
  ([`9ce8424`](https://github.com/Aohzan/glad/commit/9ce84243eb882e4481c69b77e39ba282f6b485b2))

- **property**: Allow the flat works allowance after five years of holding
  ([`a03ef85`](https://github.com/Aohzan/glad/commit/a03ef858ed51184e036c09f562eb294e4321e8b5))

- **property**: Apply a late rent revision from the claim date
  ([`d857ae4`](https://github.com/Aohzan/glad/commit/d857ae415c7dae799c61943ee90c1c3a34769821))

- **property**: Check the imported amortization tables
  ([`dd5c17a`](https://github.com/Aohzan/glad/commit/dd5c17a93facd0d1dd018489e1a844ec61dac9d3))

- **property**: Count no loan interest before the first payment
  ([`4cedd0a`](https://github.com/Aohzan/glad/commit/4cedd0aa4da4b3b9b247c93b58a13312070c5afc))

- **property**: Derive the loan balances from the amortization schedule
  ([`3d43325`](https://github.com/Aohzan/glad/commit/3d433254ddd7d00ad44c9ec0425dbcf07f7fff8f))

- **property**: Sample the projection history monthly and keep the panel parameters
  ([`dba139f`](https://github.com/Aohzan/glad/commit/dba139f011544290bccf0f9e3ffef40de8de88a2))

- **property**: Save an empty loan interest rate as zero
  ([`03ebf3e`](https://github.com/Aohzan/glad/commit/03ebf3eca651ee297ad9d587de04a0764ca4ebd7))

- **property**: Show the negative equity of underwater properties
  ([`4d8a3ab`](https://github.com/Aohzan/glad/commit/4d8a3ab087afd313ae0abc51f2898a3400256afd))

- **property**: Stop counting the loan ledger entries twice in the cash flow
  ([`3e723a6`](https://github.com/Aohzan/glad/commit/3e723a6cc08f4c3ade33248bd4e075022ea10c4e))

- **pwa**: Fetch from the network first in the service worker
  ([`c1410e0`](https://github.com/Aohzan/glad/commit/c1410e094a091c9c0c8d9fc258801cd2eccb63c9))

- **security**: Keep the raw market data errors out of the API responses
  ([`5f3d11d`](https://github.com/Aohzan/glad/commit/5f3d11d2dd36efb99c463ad3afb4203467d2226a))

- **ui**: Open the links of the clickable table rows
  ([`3dec2b4`](https://github.com/Aohzan/glad/commit/3dec2b4f58a8bdfb31d22f071c1b594ae15277a0))

### Build System

- **deps**: Bump actions/cache from 4.3.0 to 6.1.0
  ([`9b85fe4`](https://github.com/Aohzan/glad/commit/9b85fe4a9933924d6d4f48ac3f11d8ff1b0fbec6))

- **deps**: Bump apexcharts from 6.7.0 to 7.6.0
  ([`c476ad7`](https://github.com/Aohzan/glad/commit/c476ad7fe9f9e8a27c0dd746772c459d4774b786))

- **deps**: Bump apexcharts to 7.8.0, lucide-static to 1.51.0 and jscpd to 5.4.0
  ([`a5f3a10`](https://github.com/Aohzan/glad/commit/a5f3a105ff16df7aae873c558bd584824074d1b8))

- **deps**: Bump dateparser from 1.4.2 to 1.4.3
  ([`4c9c503`](https://github.com/Aohzan/glad/commit/4c9c503b5a3416d9aedde3d911c2d5e818442a52))

- **deps**: Bump django from 6.1 to 6.1.1
  ([`c37dc8c`](https://github.com/Aohzan/glad/commit/c37dc8c8005626201640fee935b7d3984abc5921))

- **deps**: Bump gitpython from 3.1.61 to 3.1.62
  ([`b7d71da`](https://github.com/Aohzan/glad/commit/b7d71daaecf7e3205ad21a0ea3a3fec8f61c8931))

- **deps**: Bump node from 24-slim to 26-slim
  ([`c7fe99c`](https://github.com/Aohzan/glad/commit/c7fe99c3bf23466775c1fa813a11b5144e4cdef1))

- **deps**: Bump urllib3 from 2.7.0 to 2.8.0
  ([`c956633`](https://github.com/Aohzan/glad/commit/c956633457df57ad78614d3aa157ca3c914b241e))

- **deps**: Bump uvicorn from 0.52.4 to 0.54.0
  ([`5d78a70`](https://github.com/Aohzan/glad/commit/5d78a705033c168545bbdb43830b59843dd6dee0))

- **deps**: Bump virtualenv from 21.7.7 to 21.7.13
  ([`e7b1d27`](https://github.com/Aohzan/glad/commit/e7b1d27ed20d6bd4f8ddf5091c821266a9e39954))

- **deps**: Update psycopg[binary] requirement from >=3.1.18 to >=3.3.6
  ([`054a5ae`](https://github.com/Aohzan/glad/commit/054a5aee965910e5326bbb3117e40d3a9ed03a32))

- **deps**: Upgrade the locked Python dependencies
  ([`fff3567`](https://github.com/Aohzan/glad/commit/fff3567aaa74d4d2bfd567fe545ac9abd9ac6970))

- **deps**: Vendor the Lucide icons and the Figtree font
  ([`01cf9ef`](https://github.com/Aohzan/glad/commit/01cf9efd890ffeb3ae0f55136c9518dcb6dc2a10))

- **deps-dev**: Bump jscpd from 4.3.0 to 5.3.2
  ([`23843ec`](https://github.com/Aohzan/glad/commit/23843ec14d3154fe9dfec7b97a83e7caebe1720a))

- **deps-dev**: List the jscpd formats as an array for jscpd 5
  ([`c427a1d`](https://github.com/Aohzan/glad/commit/c427a1d641a589d1dfae2fcf3fa18274c0cac755))

- **deps-dev**: Update setuptools requirement from >=82 to >=84.0.0
  ([`0caf47c`](https://github.com/Aohzan/glad/commit/0caf47ce0a59ade7409423da56a42c41fb432f48))

### Chores

- Remove the unused variables and type-only imports reported by CodeQL
  ([`8362412`](https://github.com/Aohzan/glad/commit/8362412de4b891da2b1c39fbd5e7cc3bcbe683ab))

- **i18n**: Translate the benchmark error to French
  ([`d864ad5`](https://github.com/Aohzan/glad/commit/d864ad5ed3405a6692d2bdf7ca876984afee84b4))

- **i18n**: Translate the household owners to French
  ([`aade1a4`](https://github.com/Aohzan/glad/commit/aade1a4ff484cc21188d51816bc7cbfdb3959a8d))

- **i18n**: Translate the loan messages to French
  ([`1d5cf97`](https://github.com/Aohzan/glad/commit/1d5cf975015be5f95f21e48927cf082d9dc138d9))

- **i18n**: Translate the new design to French
  ([`9de07e2`](https://github.com/Aohzan/glad/commit/9de07e2da0e33fd86c3123b33d93171d041dc049))

- **i18n**: Translate the owner shares, the SCPI owners and the property cash flow
  ([`858d22b`](https://github.com/Aohzan/glad/commit/858d22b65a83c19163d53b14ab79034882ecc92f))

### Continuous Integration

- Merge Dependabot minor and patch updates once CI passes
  ([`34cdd37`](https://github.com/Aohzan/glad/commit/34cdd37eaf32f3639235594668f343d32ba73209))

- Use the bot app installation permissions for Dependabot merges
  ([`a20372e`](https://github.com/Aohzan/glad/commit/a20372e1e093b4ae9a5acee0a79fa652e8e42695))

- **pre-commit**: Update the uv and ruff hooks
  ([`7733429`](https://github.com/Aohzan/glad/commit/773342972251f67d11b3c89d43c09a095221195c))

### Documentation

- Describe the loan schedules
  ([`c309827`](https://github.com/Aohzan/glad/commit/c309827617809c11dc418ab8e0051f807c7a7842))

- Describe the wealth tracking features
  ([`9d0e7e5`](https://github.com/Aohzan/glad/commit/9d0e7e5ae3c2d7f0ad78fd6c96ceec6febe99377))

- Drop the front page cache from the TODO
  ([`6afd8ae`](https://github.com/Aohzan/glad/commit/6afd8ae2bd8532e23b787d1e75e267cbdf14d0da))

### Features

- Suggest stored names, add to previous value and end chart on today
  ([`83a7802`](https://github.com/Aohzan/glad/commit/83a78023081376b7808847c1290d69a04709e3da))

- **accounts**: Add children as household members who cannot log in
  ([`c6c1941`](https://github.com/Aohzan/glad/commit/c6c19415524a104feb88fbd18bd538cf960eb3d2))

- **accounts**: Assign asset owners among the Django users
  ([`2ab189b`](https://github.com/Aohzan/glad/commit/2ab189b3b0d4119ca26cf4d841b5ad7d7177308d))

- **allocation**: Break the allocation down per household member
  ([`0d4891e`](https://github.com/Aohzan/glad/commit/0d4891e056c2b628e47a08c0a0aa91ce5e301f1a))

- **base**: Add the deadlines and operations pages
  ([`9a2b848`](https://github.com/Aohzan/glad/commit/9a2b848d05d1e801b71c93872be974b2a4dcd8fd))

- **dashboard**: List upcoming deadlines
  ([`38b9fad`](https://github.com/Aohzan/glad/commit/38b9fad40a8e32686b623c319eaa3e2308927802))

- **dashboard**: Rebuild the dashboard on the new design
  ([`e7caa96`](https://github.com/Aohzan/glad/commit/e7caa96578f24a56fffdde2d12f03c018de0e1df))

- **finance**: Break the net worth down by asset class and liquidity
  ([`5ded7e4`](https://github.com/Aohzan/glad/commit/5ded7e43c41fab4cd9ba6ca003b4ed4edad1dc64))

- **finance**: Estimate savings book interest with the fortnight rule
  ([`2b6ba7b`](https://github.com/Aohzan/glad/commit/2b6ba7b322095b27c97657b89c6dd7ddda3505fe))

- **finance**: Restyle the finance pages on the new design
  ([`32baf08`](https://github.com/Aohzan/glad/commit/32baf08953edb5b8c1a2e373e3e7b692ad6d00d7))

- **finance**: Show envelope ceilings, tax milestones and liquidity
  ([`bc19593`](https://github.com/Aohzan/glad/commit/bc19593cd5fa8fa16481fdf26d61e19ca73240ba))

- **finance**: Show the annualized performance of accounts
  ([`d00b763`](https://github.com/Aohzan/glad/commit/d00b763aba11bed2ea4ac981ed051d4de937af36))

- **finance**: Split life insurance between euro funds and units of account
  ([`6079121`](https://github.com/Aohzan/glad/commit/6079121e50a80f43a70431fd600afd2ec38b4c38))

- **finance**: Track other assets
  ([`53db33d`](https://github.com/Aohzan/glad/commit/53db33df8f10c99271c9a5611c825a7670311d7b))

- **ownership**: Choose the owners of every asset among household members
  ([`0c8294b`](https://github.com/Aohzan/glad/commit/0c8294be8d219dfc1eccafb00fe53f028b83b9bc))

- **ownership**: Name the household members by their first name only
  ([`b5949d4`](https://github.com/Aohzan/glad/commit/b5949d415fae9ffe41547a6c9c2baffb3766e6cd))

- **ownership**: Type the share of each owner and set the owners of a SCPI
  ([`1efd9d9`](https://github.com/Aohzan/glad/commit/1efd9d938a08b17d91f34e84e1dcc10e16573c2a))

- **property**: Estimate the capital gain tax of a resale
  ([`c4c897f`](https://github.com/Aohzan/glad/commit/c4c897f29ae38630289bf31f2a259373ffed6dd4))

- **property**: Rename the income and expenses report to property cash flow
  ([`e79acdb`](https://github.com/Aohzan/glad/commit/e79acdba8e751a5e4bd5b98f145fc26dbc4e725d))

- **property**: Restyle the property pages on the new design
  ([`bd957da`](https://github.com/Aohzan/glad/commit/bd957da03e66b4fefc493f1216d49265ca9d4bc2))

- **property**: Revise lease rents with the INSEE IRL
  ([`6dd8994`](https://github.com/Aohzan/glad/commit/6dd8994411215126f0d3f4074f497f4d82502c7d))

- **property**: Track the DPE rating with rental ban alerts
  ([`061dc6a`](https://github.com/Aohzan/glad/commit/061dc6afbf5191d090e433ac11c2ad4405875ff5))

- **ui**: Add an icon template tag and number format filters
  ([`fa7e2d5`](https://github.com/Aohzan/glad/commit/fa7e2d58bad53e8a8b596ec3a6a84332196a6402))

- **ui**: Add home screen icons for iOS and maskable PWA icons
  ([`337c986`](https://github.com/Aohzan/glad/commit/337c9861812bad7f23f27a08e05532ff319466f9))

- **ui**: Add the Glad design tokens and component styles
  ([`8a9c47f`](https://github.com/Aohzan/glad/commit/8a9c47f6f5eddcfc85625a02227bcb00345c8f39))

- **ui**: Fold the sidebar groups and show entry names on hover
  ([`1b4001b`](https://github.com/Aohzan/glad/commit/1b4001b554e2ad3176f62dd9a74a79ef7bd88420))

- **ui**: Rebuild the layout with a sidebar, a top bar and a search
  ([`d437d5a`](https://github.com/Aohzan/glad/commit/d437d5a1b5088f58587a08b4056dd5cfd7e48781))

- **ui**: Restyle the remaining pages on the new design
  ([`192356a`](https://github.com/Aohzan/glad/commit/192356a869c88399f361df2cf61e28971ab1d2f2))

- **ui**: Turn the top bar into a breadcrumb linking every level
  ([`8b2fbaf`](https://github.com/Aohzan/glad/commit/8b2fbaf70c34fae9e00ae23e645ee870f0782331))

- **ui**: Use the new Glad mark as logo and favicon
  ([`634474e`](https://github.com/Aohzan/glad/commit/634474e677fb293a00ec51596a1c1cfb29001c53))

### Performance Improvements

- **base**: Compute the net worth snapshots from the bulk histories
  ([`c97b2a2`](https://github.com/Aohzan/glad/commit/c97b2a2539a2db649367dff4e8c7a79a91588fd4))

- **base**: Read the SCPI prices and other asset values once for the snapshots
  ([`b79884e`](https://github.com/Aohzan/glad/commit/b79884e94ad3ee01e1a29ceb082bc15e28dffc09))

- **base**: Write the missing net worth snapshots in one query
  ([`5f7eb20`](https://github.com/Aohzan/glad/commit/5f7eb2049d92e55e8a059d0b2d76ce9e7fd584ec))

- **dashboard**: Store monthly net worth snapshots
  ([`b590ca0`](https://github.com/Aohzan/glad/commit/b590ca041f8f794b6bcb9c649249774296495119))

- **finance**: Load the account histories in bulk for the index chart
  ([`46e24d2`](https://github.com/Aohzan/glad/commit/46e24d2f0f21845d68bef61a87441f45c83c9562))

- **property**: Build each loan schedule once per request
  ([`4ca6c75`](https://github.com/Aohzan/glad/commit/4ca6c75b54dfbfd537a916410ad2622052ac27ca))

- **property**: Read the property valuations at once for the index chart
  ([`651360f`](https://github.com/Aohzan/glad/commit/651360fa87c95a31e674f90b4af635a377c0e6c5))

### Refactoring

- Read the account histories at any date or datetime
  ([`fcf6704`](https://github.com/Aohzan/glad/commit/fcf67044ccb40b9636e350ce3d4362d8d0a36ad9))

- **property**: Add a pure amortization schedule engine
  ([`3cbb422`](https://github.com/Aohzan/glad/commit/3cbb4229b7aaf18d426ec205870b2cf18000a75c))

- **property**: Compute the loan cash flows from the schedule
  ([`7ecc0dc`](https://github.com/Aohzan/glad/commit/7ecc0dca40faa6cc699c58a728ca4b84738a6a18))

- **property**: Extract the monthly flows of a property
  ([`02b3912`](https://github.com/Aohzan/glad/commit/02b3912b42e5b858551052e5673cddca6cf713a1))

- **property**: Remove the unused TAEG rate
  ([`0a50678`](https://github.com/Aohzan/glad/commit/0a506781272783ec900107a40d7acea13e055775))

- **property**: Share the loan rows between the loans panel and the loans page
  ([`6d7a4a0`](https://github.com/Aohzan/glad/commit/6d7a4a06ed2f8535abc7d7f754eb6225eb1cf4e1))

### Testing

- Check the bulk histories against the models at any date
  ([`e8c5659`](https://github.com/Aohzan/glad/commit/e8c5659aa822896db4aac4efc21622a9e0228d35))

- Check the prefetched valuations and the bulk snapshot writes
  ([`034c113`](https://github.com/Aohzan/glad/commit/034c1132396f75dbb99d8ebdd5f7134ffcf8c76e))

- Cover the new layout, dashboard, operations and deadlines
  ([`0f4c8e5`](https://github.com/Aohzan/glad/commit/0f4c8e5d118dfbe9a823819e0dcb03e9c297c935))

- Cover the owner shares, the SCPI owners, the first names and the breadcrumb
  ([`4986449`](https://github.com/Aohzan/glad/commit/4986449b143c4d56a9e6646db1d27da883562b1d))

- Cover the owners of the assets, the children and the allocation per member
  ([`f286d65`](https://github.com/Aohzan/glad/commit/f286d65a1d58f99a9d7f9987189716574478835b))

- Generate a household of two adults and a child owning the fixture assets
  ([`69a0092`](https://github.com/Aohzan/glad/commit/69a0092af0203f4e70d6c230bf14e1e14be79450))

- Generate consistent loan fixtures
  ([`147a69f`](https://github.com/Aohzan/glad/commit/147a69f38be945a9c5f5e06b2900517b4b09577e))

- **finance**: Check the bulk valuations against get_value()
  ([`e0d7940`](https://github.com/Aohzan/glad/commit/e0d79400e8550f693db6dfebcb79c937a6f8ae2b))

- **property**: Drop the assertion-less debug test
  ([`2b87658`](https://github.com/Aohzan/glad/commit/2b87658f3193068dd8178737e8f653a14ee6a132))


## v1.4.0 (2026-09-30)

### Features

- **property**: Add track records
  ([`c1d3d25`](https://github.com/Aohzan/glad/commit/c1d3d259342c12486f5837f92206565de84a2689))


## v1.3.0 (2026-09-30)

### Bug Fixes

- **finance**: Round live holding total value to 2 decimals
  ([`45b8717`](https://github.com/Aohzan/glad/commit/45b8717b7a1943657fdd8a2069ddeed54df06956))

- **i18n**: Rename French Fetch label to Actualiser
  ([`915ee2b`](https://github.com/Aohzan/glad/commit/915ee2bad031f167e6d5ee4e6d69db52e00575b6))

- **property**: Run async panel scripts with the page CSP nonce
  ([`dad0fe0`](https://github.com/Aohzan/glad/commit/dad0fe0e5da13433f37ba12e8e1254fd953c888d))

- **types**: Annotate reverse relations with RelatedManager for django-stubs 6.1.1
  ([`84be307`](https://github.com/Aohzan/glad/commit/84be30749a36593359f4c33d9d82a49e5315833a))

### Build System

- **deps**: Bump astral-sh/setup-uv from 10.1.0 to 10.2.0
  ([`3ed2487`](https://github.com/Aohzan/glad/commit/3ed2487856b2209523f83066c3dc4ba29e60871d))

- **deps-dev**: Bump django-stubs from 6.1.0 to 6.1.1
  ([`82e8ba9`](https://github.com/Aohzan/glad/commit/82e8ba922eb6dc6e1a7171a375fc3e605e727002))

- **deps-dev**: Bump ruff from 0.16.5 to 0.16.7
  ([`44444ba`](https://github.com/Aohzan/glad/commit/44444bab2c4900a354c7c4d0e77142cd205b22b5))

- **deps-dev**: Bump ruff from 0.16.7 to 0.16.8
  ([`7a6558c`](https://github.com/Aohzan/glad/commit/7a6558cb66fc4a3587542ab596f9e7999e1ad79a))

- **deps-dev**: Bump ty from 0.0.77 to 0.0.80
  ([`4fb4d8c`](https://github.com/Aohzan/glad/commit/4fb4d8c0b6394ee77b7e5fea747d8403e66eaea6))

### Chores

- Fix lint issues
  ([`725334e`](https://github.com/Aohzan/glad/commit/725334ec8a90d0ac97a76005f5b7aae7a80026e5))

### Features

- **finance**: Add Fetch all button per investment account on batch update
  ([`6e60046`](https://github.com/Aohzan/glad/commit/6e60046e71dd9cf9912945d03bfd7e51906ac0b2))


## v1.2.0 (2026-09-18)

### Bug Fixes

- Add dockerignore to avoid to include build and test files
  ([`1da71b5`](https://github.com/Aohzan/glad/commit/1da71b5e8be4dfd2c1d0830e0d8a54de894d7936))

- Auth error
  ([`77eac8a`](https://github.com/Aohzan/glad/commit/77eac8a19e622385604a44ed048387724ba018ea))

- Email notif info
  ([`98493e9`](https://github.com/Aohzan/glad/commit/98493e97f42181a8548eca8da0f2b0063d2ef3e5))

- Issue when not auth
  ([`83288cf`](https://github.com/Aohzan/glad/commit/83288cf78a7a70728b67f6b79b8374c76512a3ce))

- Kpi showing on main dashboard
  ([`7a34c04`](https://github.com/Aohzan/glad/commit/7a34c0417d5fbd7739fe8969dab6de4ad2e4bab2))

- Max digit in finance
  ([`29c1175`](https://github.com/Aohzan/glad/commit/29c11753fe9286a7c1f73faba76d62aedc7ceb17))

- Missing cash modal
  ([`748c00c`](https://github.com/Aohzan/glad/commit/748c00ca797b4e339bc81def8da65ff00a92581d))

- **ci**: Rename dependabot config to the filename GitHub reads
  ([`c702e8b`](https://github.com/Aohzan/glad/commit/c702e8b41e0e141d9da2f72956470894f0f48187))

- **dev**: Run the local Django tooling with the development environment file
  ([`a916f5d`](https://github.com/Aohzan/glad/commit/a916f5da2022dd5814640916b648c3ad5e4e879b))

- **lmnp**: Compute the fiscal result like the official forms
  ([`8e1a523`](https://github.com/Aohzan/glad/commit/8e1a5232aa32371cce5bda122ba1e6160cf1d5d6))

- **security**: Serve the health endpoint without authentication
  ([`d7008cf`](https://github.com/Aohzan/glad/commit/d7008cf3e713caef86f4a3d3ef418fe2c64b7e08))

- **settings**: Drop settings that Django no longer reads
  ([`ead30c4`](https://github.com/Aohzan/glad/commit/ead30c4578767e473c8434bff0c179baad29ca2a))

### Build System

- **deps**: Add fpdf2 for PDF generation
  ([`f9e3ea7`](https://github.com/Aohzan/glad/commit/f9e3ea715a23e1b2aa439dee599442f94815ce16))

- **release**: Let semantic-release bump the project version
  ([`b46cdf4`](https://github.com/Aohzan/glad/commit/b46cdf458af4ee3223b960f476f18369cb0885f3))

### Chores

- Allow uvicorn options
  ([`ae1ba2f`](https://github.com/Aohzan/glad/commit/ae1ba2f2e741ff9b57cc5dfd4cecdde6aaad3193))

- Bump deps
  ([`5f30a81`](https://github.com/Aohzan/glad/commit/5f30a81e36cf83f1dd5d1406f6aeac12e32689c4))

- Remove files
  ([`b57f657`](https://github.com/Aohzan/glad/commit/b57f657942175d7d119e1a830dfd547532d0decf))

- **lint**: Skip the French LMNP documents in codespell
  ([`5c74f49`](https://github.com/Aohzan/glad/commit/5c74f491148d886adc4e05aeca87571591edbca8))

### Continuous Integration

- Publish the release image and tighten workflow permissions
  ([`97fbbd6`](https://github.com/Aohzan/glad/commit/97fbbd66ebf401d55266bf2d8add553fca9576a7))

- Remove the PyPI publishing workflow
  ([`a828884`](https://github.com/Aohzan/glad/commit/a82888441cb2e518c9c215dff9fe41c18ac77b35))

- Run the checks on main and add migration, deploy and PostgreSQL jobs
  ([`bfbd2ee`](https://github.com/Aohzan/glad/commit/bfbd2ee887a2ce060aeee14cc95df1634db6ba40))

- Scan the code with CodeQL
  ([`2cdb85f`](https://github.com/Aohzan/glad/commit/2cdb85f2b961eefb07e4b4a436f64c124d0eba91))

- **pre-commit**: Pin hook revisions and make duplication checks deterministic
  ([`293c49a`](https://github.com/Aohzan/glad/commit/293c49a64c67d4a7d16479f8994ebec529724052))

### Documentation

- Document every setting, the release flow and the security policy
  ([`2aa65b4`](https://github.com/Aohzan/glad/commit/2aa65b4b5e0836cf9d1a541c4d464abb0ca48886))

- **lmnp**: Document the computation, the sources and the PDF export
  ([`c96d541`](https://github.com/Aohzan/glad/commit/c96d541bd69bb67d591e90346835a047ad02810a))

### Features

- Add email notification
  ([`118951c`](https://github.com/Aohzan/glad/commit/118951c21554dae06f8ccd5063ddd1b27fe79dce))

- Add synthesis account export
  ([`32f0b78`](https://github.com/Aohzan/glad/commit/32f0b7899f435dd99d790fdc963ff1180395ef06))

- **docker**: Build a smaller image that runs as an unprivileged user
  ([`ce9eb80`](https://github.com/Aohzan/glad/commit/ce9eb8024269062643f5628dadf574fb4eda470e))

- **finance**: Add live data
  ([`62a9fcb`](https://github.com/Aohzan/glad/commit/62a9fcb1a7048677042a579267df82e5b09165cf))

- **forms**: Initialize update_account_cash field for new InvestmentAccountDepositForm instances
  ([`a807a2b`](https://github.com/Aohzan/glad/commit/a807a2bfe9f88e29663d2c086bde658bade3033d))

- **ledger**: Add an accounting fees category
  ([`b47c5d2`](https://github.com/Aohzan/glad/commit/b47c5d25131f4579c7ebed04e03273a241a4f6db))

- **lmnp**: Amortize on a 30/360 basis from the LMNP activity start date
  ([`a862abb`](https://github.com/Aohzan/glad/commit/a862abb48aebbec10f3e59328e81da33bbad8be0))

- **lmnp**: Freeze the liasse of a fiscal year and export it as PDF
  ([`764f8ed`](https://github.com/Aohzan/glad/commit/764f8ed6e7e79cdd5cf3fdbba91088edb03d2674))

- **property**: Add address and estimation from online
  ([`5b6ceb7`](https://github.com/Aohzan/glad/commit/5b6ceb7a8f95df2bc2c0abebba89175424b754ee))

- **property**: All loans page
  ([`954bec4`](https://github.com/Aohzan/glad/commit/954bec41fb4f85160b2bf2a3c64bb53d36ae23a9))

- **scpi**: Add batch update
  ([`ad7113c`](https://github.com/Aohzan/glad/commit/ad7113c1f39186a7ee2858725a07c69cab5d8588))

- **scpi**: Add theoretical value
  ([`b2c5b34`](https://github.com/Aohzan/glad/commit/b2c5b349fb511d44416ff555de5492a793153f75))

- **security**: Derive the HTTPS settings from APP_URL
  ([`b221e7b`](https://github.com/Aohzan/glad/commit/b221e7bfe92678067b411936ab5a66c2cab4e319))

- **security**: Send a Content-Security-Policy with per-response nonces
  ([`03ba73b`](https://github.com/Aohzan/glad/commit/03ba73bfbae4e456e09c5214c3bc93e4636a68df))

- **settings**: Tune database connections and the email timeout
  ([`1c34828`](https://github.com/Aohzan/glad/commit/1c34828d80685bec73fc1d3477ec61d545b1e19b))

### Refactoring

- Code structure for improved readability and maintainability
  ([`f82b4bf`](https://github.com/Aohzan/glad/commit/f82b4bf3690b6152fb2e9f3439f67f06c0227b17))

- **lmnp**: Split the accounting dashboard into one include per cerfa form
  ([`6f32c67`](https://github.com/Aohzan/glad/commit/6f32c67fcfa5a4fc05f1ed9d2e6b314a3fb625e6))

### Testing

- **investment_account**: Add regression test for value calculation excluding future holdings
  ([`804705b`](https://github.com/Aohzan/glad/commit/804705badea6af772f061e4cd5ba4d953249563e))

- **lmnp**: Golden tests from the reference workbook
  ([`6e4b8db`](https://github.com/Aohzan/glad/commit/6e4b8dbd1881d3c9bb1311f4f7e2a7eca937f4c0))


## v1.1.0 (2026-09-07)

### Chores

- Fix pip publishing
  ([`e51e560`](https://github.com/Aohzan/glad/commit/e51e56081c96be0b5805c0e08c01cf1784082789))

### Continuous Integration

- Add pypi
  ([`2fb8376`](https://github.com/Aohzan/glad/commit/2fb8376e05ddab9ced32e721ce847050e438fd3b))

- **docker**: Push on latest tag
  ([`a3748b7`](https://github.com/Aohzan/glad/commit/a3748b73ced2222ecfac9df44d0542599c28f341))

### Features

- Replace passkey button with conditional UI on login
  ([`86a4b6a`](https://github.com/Aohzan/glad/commit/86a4b6ac1046bc2f56227c37482c71f14e18b135))

- Squash db migration
  ([`d98b421`](https://github.com/Aohzan/glad/commit/d98b421c5f191bcbe3295dd63f26a8221ab94dd3))


## v1.0.0 (2026-06-03)

- Initial Release
