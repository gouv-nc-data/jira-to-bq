# Template d'une fonction export de l'api jira vers bigquery'


# Exécution locale
```
pip install -r requirements.txt
python main.py
```
Récupérer les credentials du compte de service et les placer dans le projet.  
S'assurer que le compte de service dispose des droits nécessaires (ex: ajout en lecture sur fichier Drive)  

# Exécution cloud automatisée 
Faire un push sur le repo pour lancer le déploiement automatique.  
L'exécution se fera selon le schedule défini dans le gitops.  
Il est possible de la déclencher manuellement via Workflow ou Cloud Scheduler sous GCP.


# Exécution dans un container
## install pack
```
sudo add-apt-repository ppa:cncf-buildpacks/pack-cli
sudo apt-get update
sudo apt-get install pack-cli
```

## construction de l'image
```
pack build  --builder gcr.io/buildpacks/builder:v1 \
  --env GOOGLE_FUNCTION_SIGNATURE_TYPE=http \
  --env GOOGLE_FUNCTION_TARGET=${APPLICATION} \
  --env GOOGLE_PYTHON_VERSION="3.10.x" \
  ${APPLICATION}-function
```

## lancement de l'image en local
```
docker run --rm -p 8080:8080 ${APPLICATION}-function
```

## Appel de la fonction
```
curl localhost:8080
```

