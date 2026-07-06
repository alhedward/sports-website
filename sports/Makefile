.PHONY: fmt deploy output seed destroy zip

fmt:
	terraform -chdir=terraform fmt -recursive
	python3 -m py_compile lambda/api/handler.py lambda/ingest/handler.py scripts/seed_data.py admin_manager/sports_admin_manager.py

deploy:
	terraform -chdir=terraform init
	terraform -chdir=terraform apply

output:
	terraform -chdir=terraform output

seed:
	aws lambda invoke \
		--function-name "$$(terraform -chdir=terraform output -raw ingest_lambda_name)" \
		--cli-binary-format raw-in-base64-out \
		--payload '{}' \
		/tmp/global-sports-seed-response.json
	cat /tmp/global-sports-seed-response.json

destroy:
	terraform -chdir=terraform destroy

zip:
	cd .. && zip -r sports-vk2ale-poc.zip sports -x 'sports/.git/*' 'sports/.terraform/*' 'sports/*.zip'
