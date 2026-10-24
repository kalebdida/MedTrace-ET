# MedTrace-ET backend: AWS Lambda container image.
#
#   docker build -t medtrace-backend backend/
#   docker run --rm -p 9000:8080 -e SCAN_TABLE_NAME=... medtrace-backend
#
# The base image bundles the Lambda Runtime Interface Emulator, so the
# container can be invoked locally on port 9000 (see backend/README.md).
FROM public.ecr.aws/lambda/python:3.13

COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

COPY app.py ${LAMBDA_TASK_ROOT}/
COPY medtrace/ ${LAMBDA_TASK_ROOT}/medtrace/
COPY visual_model/ ${LAMBDA_TASK_ROOT}/visual_model/

CMD ["app.lambda_handler"]
