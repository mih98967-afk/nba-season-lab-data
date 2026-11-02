# NBA Season Lab v6.16 - existing Hosting only

1. Export a backup of your personal team in Profile, and separately export local price and decision journals if they matter.
2. Upload the ZIP to the **existing** Firebase Cloud Shell home directory.
3. Run these commands (no new project and no Blaze):

```sh
unzip -qo ~/NBA_Season_Lab_v6_16_Explainable_Transfers.zip -d ~
cd ~/nba-season-lab-v616
firebase deploy --only hosting --project nba-season-lab
```

4. Refresh https://nba-season-lab.web.app and confirm the header is v6.16. Compare live roster/cash/transfers with Sports.ru; do not save personal state if mismatched. On Transfers -> Compare, expand the explanation 'Откуда берутся FP' and check that the sum matches the selected route's gross gain (not its heuristic net).
5. This is manual owner deploy. A GitHub merge alone never deploys Firebase Hosting.
