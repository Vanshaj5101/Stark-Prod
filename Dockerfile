# Use the official AWS Lambda Python 3.8 base image
FROM public.ecr.aws/lambda/python:3.12

# Copy the lambda_handler.py file into the container
COPY lambda_handler.py ${LAMBDA_TASK_ROOT}

# Install any necessary dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Command to run the Lambda function
CMD [ "lambda_handler.lambda_handler" ]