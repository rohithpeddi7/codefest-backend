from rest_framework import serializers
from .utils import FirebaseAPI
from .models import *
from website.models import Profile,ValidReferral
from django.conf import settings
from rest_framework.exceptions import ParseError

class LoginSerializer(serializers.Serializer):
    id_token = serializers.CharField(max_length=2400, required=False)
    provider_token = serializers.CharField(max_length=2400, required=False)

    def validate_access_token(self, access_token):
        return FirebaseAPI.verify_id_token(access_token)

    def validate(self, attrs):
        id_token = attrs.get('id_token', None)
        provider_token = attrs.get('provider_token', None)

        user = None

        if id_token:
            jwt = self.validate_access_token(id_token)
            uid = jwt['uid']
            provider=FirebaseAPI.get_provider(jwt)
            
            try:
                account = VerifiedAccount.objects.get(pk=uid)
            except VerifiedAccount.DoesNotExist:
                raise serializers.ValidationError('No such account exists')
            
            user = account.user
            if provider == VerifiedAccount.AUTH_EMAIL_PROVIDER:
                if not account.is_verified:
                    account.is_verified=FirebaseAPI.get_email_confirmation_status(uid)
                    account.save()
            # add the verification status to the validated data 
            attrs['is_verified']=account.is_verified   
            profile=user.profile
            # because we also need the frontend to know if the profile is complete
            attrs['is_profile_complete']=profile.is_profile_complete
            """
            If used a referral code, and if account is verfied, and if profile is complete,
            then add the referral to the referral model which is final
            """ 

            if profile.is_profile_complete and profile.referred_by and attrs['is_verified']:
                if not hasattr(profile,'referral'):
                    referral=ValidReferral.objects.create(by=profile.referred_by,to=profile)

            if provider_token:
                account.provider_token = provider_token
                account.save()
        else:
            raise ParseError('Provide access_token or username to continue.')
        # Did we get back an active user?
        if user:
            if not user.is_active:
                raise serializers.ValidationError('User account is disabled.')
        else:
            raise serializers.ValidationError(
                'Unable to log in with provided credentials.')

        attrs['user'] = user
        return attrs


class RegisterSerializer(serializers.Serializer):
    
    id_token = serializers.CharField(max_length=2400, required=True)
    provider_token = serializers.CharField(max_length=2400, required=False)
    first_name = serializers.CharField(max_length=40, allow_blank=False)
    last_name = serializers.CharField(max_length=100, allow_blank=True)
    applied_referral_code = serializers.CharField(max_length=500,required=False)

    def validate_id_token(self, access_token):
        return FirebaseAPI.verify_id_token(access_token)

    def validate_first_name(self,name):
        if name==None or name=='':
            raise serializers.ValidationError("First Name cannot be blank")
        return name

    def validate_applied_referral_code(self,code):
        if code==None:
            return None
        try:
            referred_by=Profile.objects.get(refferal_code=code)
        except:
            raise serializers.ValidationError("Invalid Referral Code")
        return referred_by
        
    def get_user(self, data,uid):
        user = User()
        user.username = uid
        user.first_name = data.get('first_name')
        user.last_name = data.get('last_name')
        user.gender = data.get('gender')
        return user

        
    def save(self):
        data = self.validated_data
        jwt = data.get('id_token')
        uid = jwt['uid']
        provider = FirebaseAPI.get_provider(jwt)
        provider_uid = FirebaseAPI.get_provider_uid(jwt, provider)
        user = self.get_user(data,uid)
        try:
            user.validate_unique()
        except Exception as e:
            raise serializers.ValidationError(detail=e.message_dict)
        account, _ = VerifiedAccount.objects.get_or_create(
            uid=uid, user=user, provider=provider, provider_uid=provider_uid,
            provider_token=data.get('provider_token'))
        if provider == VerifiedAccount.AUTH_EMAIL_PROVIDER:
            account.is_verified=False
            account.save()
        profile,_ = Profile.objects.get_or_create(user=user,referred_by=data.get('applied_referral_code',None))
        profile.save()
        user.save()
        return user