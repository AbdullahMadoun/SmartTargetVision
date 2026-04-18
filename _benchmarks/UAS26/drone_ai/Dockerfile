FROM nvcr.io/nvidia/l4t-ml:r36.3.0-py3

WORKDIR /app

COPY requirements.txt .

RUN apt-get update && apt-get install -y \
    python3-pip \
    python3-opencv \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --upgrade pip
RUN pip3 install -r requirements.txt

COPY . .

ENV OS_ENV='jetson'
ENV MODEL_TYPE='std'
ENV CONNECTION_STRING='/dev/ttyTHS1'
ENV BAUD_RATE='921600'
ENV CAM_INDEX='0'
ENV TARGET_IDEAL_AREA='50000'
ENV VERTICAL_DEADZONE='5000'
ENV HORIZONTAL_DEADZONE='25'
ENV VERTICAL_VELOCITY='false'
ENV SPEED_SAFETY='false'

CMD ["python3", "main.py"]