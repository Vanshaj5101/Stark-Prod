# # Use the official AWS Lambda Python 3.8 base image
# FROM public.ecr.aws/lambda/python:3.12

# # Copy the lambda_handler.py file into the container
# COPY lambda_handler.py ${LAMBDA_TASK_ROOT}

# # Install any necessary dependencies
# COPY requirements.txt .
# RUN pip install -r requirements.txt

# # Command to run the Lambda function
# CMD [ "lambda_handler.lambda_handler" ]

# Use the official Python image from the Docker Hub
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements.txt file to install dependencies
COPY requirements.txt .

# Install the necessary dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Gunicorn
RUN pip install gunicorn

# Copy the entire application code to the working directory
COPY . .

# Set environment variables if needed (you can also pass these when running the container)
# ENV SLACK_BOT_TOKEN=your_token
# ENV SLACK_SIGNING_SECRET=your_signing_secret
# ENV SLACK_BOT_USER_ID=your_user_id
# ENV OPEN_AI_API_KEY=your_openai_api_key

# Expose the port the app runs on
EXPOSE 4040

# Use Gunicorn as the production server to run the Flask app
CMD ["gunicorn", "-b", "0.0.0.0:4040", "flask_app:stark", "--workers=4"]

# Replace `your_script_name:stark` with the actual name of your Flask app
# In your case, `stark` is the Flask app object in your Python file.
