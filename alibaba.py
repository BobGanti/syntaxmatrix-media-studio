from __future__ import annotations

import os, dashscope

from http import HTTPStatus
from dashscope import MultiModalConversation, VideoSynthesis


# class AlibabaAudio:
#     """A wrapper class for Alibaba DashScope multimodal audio generation endpoints."""

#     def __init__(self, api_key: str, base_http_api_url: str):
#         self.api_key = api_key
#         self.base_http_api_url = base_http_api_url


#     def clone_voice(api_key: str, model: str, voice: str, text: str, stream: bool=False):
#         print("Generating speech response...")
#         response = dashscope.MultiModalConversation.call(
#             api_key=api_key,
#             model=model,
#             text=text,
#             voice=voice,
#             stream=stream
#         )

#         return response


#     def text2speech(self, model: str, text: str, voice: str, stream: bool=False):
#         dashscope.base_http_api_url = self.base_http_api_url
#         response = MultiModalConversation.call(
#             api_key=self.api_key,
#             model=model,
#             text=text,
#             voice=voice,
#             stream=stream
#         )
#         return response


class AlibabaImages:
    """A wrapper class for Alibaba DashScope multimodal image generation endpoints."""

    def __init__(self, api_key,):
        self.api_key = api_key
        

    def text2image(self, model, messages, url):     
        api_key = self.api_key
        dashscope.base_http_api_url = url
        response = MultiModalConversation.call(
            api_key=api_key,
            model=model,
            messages=messages,
            result_format='message',
            stream=False,
            watermark=False,
            prompt_extend=True,
            negative_prompt='',
            size='1328*1328'
        )

        if response.status_code == 200:
            # Extract the image URL from the nested structure
            image_url = response["output"]["choices"][0]["message"]["content"][0]["image"]

            return image_url

        else:
            print(f"HTTP status code: {response.status_code}")
            print(f"Error code: {response.code}")
            print(f"Error message: {response.message}")


    # =================================================
    # Ref
    # =================================================
    def edit2image(self, model, prompt, url):
        dashscope.base_http_api_url = url
        messages = prompt
                
        response = MultiModalConversation.call(
            api_key=self.api_key,
            model=model,
            messages=messages,
            result_format='message',
            stream=False,
            n=2,
            watermark=True,
            negative_prompt=""
        )

        if response.status_code == 200:
            content_list = response["output"]["choices"][0]["message"]["content"]
            return content_list
        else:
            print(f"HTTP status code: {response.status_code}")
            print(f"Error code: {response.code}")
            print(f"Error message: {response.message}")


class AlibabaVideos:
    """A wrapper class for Alibaba DashScope multimodal video generation endpoints."""

    def __init__(
            self, api_key: str, 
            base_http_api_url: str,
    ):
        self.api_key = api_key
        self.base_http_api_url = base_http_api_url


    def text2video_lipsync(
            self, 
            model: str, 
            prompt: str, 
            audio_url: str,
            size: str='1280*720',
            resolution: str = "720P",
            duration: int = 10,     
            seed: int=12345,
            negative_prompt="",
            prompt_extend: bool=True,
            watermark: bool=False,
    ):
        dashscope.base_http_api_url = self.base_http_api_url

        print('----Synchronous call, please wait a moment----')
        print('Please wait...')
        rsp = VideoSynthesis.call(
            api_key=self.api_key,
            model=model,
            prompt=prompt,
            audio_url=audio_url,
            size=size,
            resolution=resolution,
            duration=duration,
            seed=seed,
            negative_prompt=negative_prompt,
            prompt_extend=prompt_extend,
            watermark=watermark,     
        )

        if rsp.status_code == HTTPStatus.OK:
            return rsp.output.video_url
        else:
            return ('Failed. Status code: %s, code: %s, message: %s' %
                (rsp.status_code, rsp.code, rsp.message))


    def image2video_lipsync(
            self, 
            model: str, 
            prompt: str, 
            media, 
            url: str,
            resolution: str = "720P",
            duration: int = 10,
            watermark: bool = False,
    ):
        api_key = self.api_key
        dashscope.base_http_api_url = url

        print('----Synchronous call, please wait a moment----')
        rsp = VideoSynthesis.call(
            api_key=api_key,
            model=model,
            media=media,
            resolution=resolution,  # Options: "480P", "720P"
            duration=duration,
            prompt_extend=True,
            watermark=watermark,
            seed=12345, 
            negative_prompt = "", 
            prompt=prompt,    
        )

        if rsp.status_code == HTTPStatus.OK:
            return rsp.output.video_url


    def reference2video(
            self, 
            model: str, 
            prompt: str, 
            media, 
            url: str,
            resolution: str="720P",
            duration: int=10,
            ratio: str="16:9",
            prompt_extend: bool=True,
            watermark: bool=False,
    ):
        
        api_key = self.api_key

        print('please wait...')
        rsp = VideoSynthesis.call(
            api_key=api_key,
            model=model,
            media=media,
            prompt=prompt,
            resolution=resolution,
            ratio=ratio,
            duration=duration,
            prompt_extend=prompt_extend,
            watermark=watermark,
        )
        print(rsp)
        if rsp.status_code == HTTPStatus.OK:
            return rsp.output.video_url
        else:
            print('Failed, status_code: %s, code: %s, message: %s' %
                (rsp.status_code, rsp.code, rsp.message))
