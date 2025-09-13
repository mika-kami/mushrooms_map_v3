# Use the official AWS Lambda base image for Python 3.12
# This image is optimized for Lambda and includes the runtime interface client.
FROM public.ecr.aws/lambda/python:3.12

# Copy the requirements file into the image's working directory.
COPY requirements.txt .

# Install the Python dependencies from requirements.txt.
# The --no-cache-dir flag is used to reduce the final image size.
RUN pip install -r requirements.txt --no-cache-dir

# Copy your bot's source code from your local 'src' folder
# to the /var/task/ directory inside the container, which is Lambda's working directory.
COPY src/ /var/task/

# Set the command that Lambda will execute when the function is invoked.
# The format is "filename.handler_function_name".
# Replace 'app.lambda_handler' with your actual file and handler name if they are different.
CMD [ "app.lambda_handler" ]
