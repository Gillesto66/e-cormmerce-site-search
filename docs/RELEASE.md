# Procédure de publication

Les trois paquets partagent le même numéro de version. Ordre à respecter :

1. **Versions** — `python-engine/pyproject.toml`, `js-engine/package.json` (+ `package-lock.json`), `CHANGELOG.md`.
   (Composer n'a pas de champ version : c'est le tag git du dépôt Packagist qui fait foi.)
2. **Fichiers dérivés** — `python shared-assets/generate_reference.py --check`, `python scripts/sync_fixtures.py`.
3. **Tests** — `pytest` (python-engine), `npm test` (js-engine), `vendor/bin/phpunit` (php-engine).
4. **Miroir PHP** — `python scripts/sync_php_repo.py ../php-e-cormmerce-search`, puis tests dans ce dépôt.
5. **Tags** — `vX.Y.Z` dans le monorepo et dans `php-e-cormmerce-search`.
6. **Publication** (après relecture) :
   - PyPI : `python -m build` dans `python-engine/` puis `twine upload dist/*`, ou le workflow `release.yml` (publication de confiance).
   - npm : `npm publish --access public` dans `js-engine/` (le script `prepublishOnly` rejoue typecheck, tests et build).
   - Packagist : le webhook GitHub du dépôt `php-e-cormmerce-search` détecte le tag.

Une version publiée sur PyPI ou npm **ne peut pas être republiée** : en cas d'erreur, publier X.Y.(Z+1).
