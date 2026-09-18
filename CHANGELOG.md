# CHANGELOG

<!-- version list -->

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
