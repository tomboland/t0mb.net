{-# LANGUAGE OverloadedStrings #-}
-- Shared metadata, tag naming and escaped template values; no cinema policy.
module View where

import Crypto.Hash (Digest, SHA256, hash)
import Data.Aeson (Value(..), toJSON)
import qualified Data.Aeson.Key as K
import qualified Data.Aeson.KeyMap as KM
import qualified Data.ByteString as BS
import Data.Char (isAscii, isAlphaNum)
import Data.List (intercalate)
import qualified Data.Map.Strict as M
import Data.Maybe (fromMaybe)
import Data.Scientific (formatScientific, FPFormat(Fixed))
import qualified Data.Text as T
import qualified Data.Text.Encoding as TE
import Data.Text.Normalize (normalize, NormalizationMode(..))
import qualified Data.Yaml as Y
import Hakyll

get :: String -> Value -> Value
get key (Object o) = fromMaybe Null (KM.lookup (K.fromString key) o)
get _ _ = Null
text :: Value -> String
text (String s) = T.unpack s
text (Number n)
  | fromInteger (round n) == n = show (round n :: Integer)
  | otherwise = formatScientific Fixed Nothing n
text _ = ""
val :: String -> Value
val = String . T.pack
str :: String -> Value -> String
str key = text . get key
arr :: Value -> [Value]
arr (Array a) = foldr (:) [] a
arr _ = []
ls :: String -> Value -> [Value]
ls key = arr . get key
truth :: Value -> Bool
truth Null = False
truth (Bool b) = b
truth (String s) = not (T.null s)
truth (Array a) = not (null a)
truth (Object a) = not (KM.null a)
truth _ = True
set :: [(String, Value)] -> Value -> Value
set fields v = Object $ foldr (uncurry (KM.insert . K.fromString)) original fields
  where original = case v of Object o -> o; _ -> KM.empty
obj :: [(String, Value)] -> Value
obj fields = set fields Null
values :: [Value] -> Value
values = toJSON
number :: Int -> Value
number = val . show
foldCase :: String -> String
foldCase = T.unpack . T.toCaseFold . T.pack
slug :: String -> String
slug = intercalate "-" . filter (not . null) . words . map replace . T.unpack . T.toLower . T.filter isAscii . normalize NFKD . T.pack
  where replace c = if isAlphaNum c then c else ' '
normalTags :: Value -> Either String [String]
normalTags Null = Right []
normalTags (Array a) = do
  labels <- mapM clean (foldr (:) [] a)
  pure $ M.elems $ M.fromListWith (flip const) [(foldCase s,s) | s <- labels]
  where clean (String s) | not (T.null $ T.strip s) = Right $ T.unpack $ normalize NFC $ T.unwords $ T.words s
        clean _ = Left "Tags must be non-empty strings"
normalTags _ = Left "Tags must be a list"
tagUrlIn :: String -> String -> String
tagUrlIn base label = base ++ prefix ++ "-" ++ take 12 digest ++ "/"
  where key = foldCase label
        prefix = case take 60 (slug key) of "" -> "tag"; s -> s
        digest = show (hash (TE.encodeUtf8 $ T.pack key) :: Digest SHA256)
routePath :: String -> FilePath
routePath url = dropWhile (=='/') url ++ "index.html"

readDocument :: FilePath -> IO Value
readDocument path = do
  contents <- T.unpack . TE.decodeUtf8 <$> BS.readFile path
  case lines contents of
    "---":rest -> case break (=="---") rest of
      (header,_:body) -> case Y.decodeEither' (TE.encodeUtf8 $ T.pack $ unlines header) of
        Left e -> fail (path ++ ": " ++ show e)
        Right meta -> pure $ set [("source", val path), ("rawBody", val $ unlines body)] meta
      _ -> fail (path ++ ": missing front matter terminator")
    _ -> fail (path ++ ": missing front matter")

-- JSON-shaped view records let templates consume lists and optional fields without
-- constructing HTML in Haskell. Only Markdown compiler results bypass escaping.
valueContext :: Context Value
valueContext = Context $ \key _ item -> case get key (itemBody item) of
  Null -> noResult $ "No field "++key
  String "" -> noResult $ "Empty field "++key
  Bool False -> noResult $ "False field "++key
  Array xs | null xs -> noResult $ "Empty field "++key
  Array xs -> pure $ ListField valueContext [Item (fromFilePath $ show n) v | (n,v) <- zip [0::Int ..] (foldr (:) [] xs)]
  Object o | KM.null o -> noResult $ "Empty field "++key
  v@(Object _) -> pure $ ListField valueContext [Item (fromFilePath key) v]
  Bool True -> pure EmptyField
  v -> pure $ StringField $ if key `elem` ["intro", "htmlBody"] then text v else escapeHtml (text v)
viewContext :: Value -> Context String
viewContext v = bodyField "body" <> Context (\k args i -> unContext valueContext k args (Item (itemIdentifier i) v))

