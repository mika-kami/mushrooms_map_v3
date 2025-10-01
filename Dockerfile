# Use the official AWS Lambda base image for Python 3.12
FROM public.ecr.aws/lambda/python:3.12

# Copy the requirements file into the Lambda task root
COPY requirements.txt ${LAMBDA_TASK_ROOT}

# Install the Python dependencies from requirements.txt
# Use --target to install to the Lambda task root directory
RUN pip install -r requirements.txt --target "${LAMBDA_TASK_ROOT}" --no-cache-dir

# Copy your bot's source code from your local 'src' folder
# to the Lambda task root directory
COPY src/ ${LAMBDA_TASK_ROOT}/

# Set the command that Lambda will execute when the function is invoked
# Format is "filename.handler_function_name"
# This assumes you have a file named 'app.py' with a function 'lambda_handler'
CMD ["app.lambda_handler"]
